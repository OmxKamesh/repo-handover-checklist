import importlib.util
import json
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('handoff_pack', Path(__file__).resolve().parents[1] / 'scripts' / 'handoff_pack.py')
hp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hp)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.run_git('init', '-q')

    def run_git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True).stdout

    def stage(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        self.run_git('add', '--', name)

    def test_index_evidence_and_line_is_exact(self):
        self.stage('README.md', '# Toy\n\n## Setup\nDo the thing\n## Tests\n')
        oid = self.run_git('rev-parse', ':README.md').decode().strip()
        (self.repo / 'README.md').write_text('Unstaged replacement')
        result = hp.generate(self.repo)
        setup = next(x for x in result['evidence'] if x['topic'] == 'setup')
        self.assertEqual((setup['line'], setup['blob']), (3, oid))
        self.assertEqual({x['topic'] for x in result['open_questions']}, {'operations', 'ownership'})

    def test_no_contents_or_untracked_secret_leak(self):
        self.stage('README.md', 'Setup\nsecret-value-DO-NOT-EMIT\n')
        self.stage('.env', 'TOKEN=SUPERSECRET')
        (self.repo / 'untracked.md').write_text('Deployment untracked-private')
        report = hp.generate(self.repo)
        output = json.dumps(report) + hp.markdown(report)
        for value in ['secret-value-DO-NOT-EMIT', 'SUPERSECRET', '.env', 'untracked-private', 'untracked.md']:
            self.assertNotIn(value, output)
        self.assertEqual(report['excluded_counts']['sensitive_names'], 1)

    def test_scripts_are_never_executed(self):
        self.stage('package.json', '{"scripts":{"test":"touch OWNED"}}')
        self.stage('setup.py', "raise RuntimeError('must never run')")
        report = hp.generate(self.repo)
        self.assertEqual(len(report['evidence']), 2)
        self.assertFalse((self.repo / 'OWNED').exists())

    def test_repository_fsmonitor_is_not_executed(self):
        self.stage('README.md', 'Setup\n')
        marker = self.repo / 'FSMONITOR_EXECUTED'
        hook = self.repo / ('monitor.cmd' if os.name == 'nt' else 'monitor.sh')
        program = ('@echo touched > "' + str(marker) + '"\n' if os.name == 'nt' else
                   '#!/bin/sh\nprintf touched > ' + shlex.quote(marker.as_posix()) + '\n')
        hook.write_text(program, encoding='utf-8')
        hook.chmod(0o755)
        self.run_git('config', 'core.fsmonitor', hook.as_posix())
        # Positive control proves this benign fixture would execute without the override.
        self.run_git('status', '--porcelain')
        self.assertTrue(marker.exists(), 'fsmonitor positive control must execute')
        marker.unlink()
        hp.generate(self.repo)
        self.assertFalse(marker.exists(), 'metadata generation must disable repository fsmonitor')

    def test_binary_and_large_docs_are_skipped(self):
        self.stage('binary.md', 'Setup\x00payload')
        self.stage('large.md', 'Setup' + 'x' * hp.MAX_BLOB)
        report = hp.generate(self.repo)
        self.assertEqual(report['evidence'], [])
        self.assertEqual(report['excluded_counts']['oversized'], 1)
        self.assertEqual(report['excluded_counts']['binary_or_invalid'], 1)

    def test_keyword_is_not_verification(self):
        self.stage('README.md', 'No setup or deployment or testing or owner exists.')
        report = hp.generate(self.repo)
        self.assertEqual(report['status'], 'inventory_only')
        self.assertTrue(all(x['basis'] == 'keyword_location_not_verified_procedure' for x in report['evidence']))

    def test_symlink_blob_is_not_followed(self):
        self.stage('placeholder', 'Setup\n')
        oid = self.run_git('rev-parse', ':placeholder').decode().strip()
        self.run_git('update-index', '--add', '--cacheinfo', '120000', oid, 'linked.md')
        report = hp.generate(self.repo)
        self.assertEqual(report['excluded_counts']['nonregular'], 1)
        self.assertFalse(any(x['path'] == 'linked.md' for x in report['evidence']))

    def test_invalid_repository_fails(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaises(ValueError):
                hp.generate(other)

    def test_empty_repository_has_questions(self):
        report = hp.generate(self.repo)
        self.assertEqual(report['tracked_entries'], 0)
        self.assertEqual(len(report['open_questions']), 4)

    def test_declarations_are_unverified_and_commands_omitted(self):
        self.stage('ops.md', 'Runbook\n')
        result = hp.generate(self.repo, {'procedures': [{'topic': 'operations', 'path': 'ops.md', 'line': 1, 'commands': ['TOKEN=never-output deploy']} ]})
        item = result['evidence'][0]
        self.assertEqual(item['commands_status'], 'unverified_not_executed')
        self.assertEqual(item['command_count'], 1)
        self.assertNotIn('never-output', json.dumps(result))

    def test_invalid_declaration_paths_and_lines(self):
        self.stage('ops.md', 'Runbook\n')
        for path in ['../outside.md', '/outside.md', 'C:/outside.md', '.env', 'missing.md', '..\\outside.md']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                hp.generate(self.repo, {'procedures': [{'topic': 'operations', 'path': path}]})
        with self.assertRaises(ValueError):
            hp.generate(self.repo, {'procedures': [{'topic': 'operations', 'path': 'ops.md', 'line': 2}]})
        with self.assertRaises(ValueError):
            hp.generate(self.repo, {'procedures': [{'topic': [], 'path': 'ops.md'}]})

    def test_commit_detached_and_dirty_metadata(self):
        self.stage('README.md', 'Setup\n')
        self.run_git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'Synthetic fixture')
        clean = hp.generate(self.repo)
        self.assertFalse(clean['dirty'])
        self.assertIsNotNone(clean['commit'])
        self.run_git('checkout', '--detach', '-q')
        (self.repo / 'README.md').write_text('changed')
        dirty = hp.generate(self.repo)
        self.assertTrue(dirty['dirty'])
        self.assertIsNone(dirty['branch'])
        self.assertEqual(clean['commit'], dirty['commit'])

    def test_cli_exit_codes(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(hp.main([str(self.repo)]), 1)
            self.stage('README.md', 'Setup testing owner rollback')
            self.assertEqual(hp.main([str(self.repo)]), 0)
            self.assertEqual(hp.main([str(self.repo / 'missing')]), 2)

    def test_output_exclusive_creation(self):
        import contextlib
        import io
        self.stage('README.md', 'Setup testing owner rollback')
        target = self.repo / 'handoff.json'
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(hp.main([str(self.repo), '--format', 'json', '--output', str(target)]), 0)
            original = target.read_bytes()
            self.assertEqual(json.loads(original)['snapshot'], 'git_index')
            self.assertEqual(hp.main([str(self.repo), '--output', str(target)]), 2)
            self.assertEqual(target.read_bytes(), original)

    def test_markdown_escapes_hostile_path(self):
        report = {'evidence': [{'topic': 'setup', 'path': '<img>`\n[click](https://bad)', 'line': 1, 'blob': 'a'*40, 'basis': 'file_present'}], 'open_questions': [], 'limitations': []}
        output = hp.markdown(report)
        self.assertNotIn('<img>', output)
        self.assertIn('\\u0060', output)


if __name__ == '__main__':
    unittest.main()

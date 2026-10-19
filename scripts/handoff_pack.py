#!/usr/bin/env python3
"""Build a content-free operational evidence map from the Git index."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

MAX_BLOB = 1024 * 1024
TOPICS = {
    'setup': re.compile(r'\b(install|installation|setup|quickstart)\b', re.I),
    'operations': re.compile(r'\b(deploy|deployment|rollback|backup|restore|monitoring)\b', re.I),
    'ownership': re.compile(r'\b(owner|maintainer|support|contact)\b', re.I),
    'testing': re.compile(r'\b(test|tests|testing)\b', re.I),
}


def git_command(repo, *args):
    # Even read-only status can execute a repository-configured fsmonitor hook.
    # Disable it on every invocation; never use checkout/filter/diff/textconv paths.
    return ['git', '--no-pager', '--no-optional-locks', '-c', 'core.fsmonitor=false',
            '-C', str(repo), *args]


def git(repo, *args):
    result = subprocess.run(git_command(repo, *args), capture_output=True, check=False)
    if result.returncode:
        raise ValueError('Git read failed; confirm this is an accessible repository with a valid index.')
    return result.stdout


def sensitive(path):
    name = PurePosixPath(path).name.lower()
    return (name.startswith('.env') or any(x in name for x in ('secret', 'credential', 'private-key'))
            or name.endswith(('.pem', '.key', '.p12', '.pfx')))


def optional_git(repo, *args):
    result = subprocess.run(git_command(repo, *args), capture_output=True, check=False)
    return result.stdout.decode('utf-8', errors='replace').strip() if result.returncode == 0 else None


def validate_declaration(repo, declaration, indexed):
    if not isinstance(declaration, dict) or set(declaration) != {'procedures'} or not isinstance(declaration['procedures'], list):
        raise ValueError('Declaration must contain only a procedures array.')
    result = []
    for item in declaration['procedures']:
        if not isinstance(item, dict) or not {'topic', 'path'} <= set(item) or set(item) - {'topic', 'path', 'line', 'commands'}:
            raise ValueError('Invalid procedure declaration fields.')
        topic, path = item['topic'], item['path']
        if not isinstance(topic, str) or topic not in TOPICS or not isinstance(path, str):
            raise ValueError('Invalid declaration topic or path.')
        parts = PurePosixPath(path)
        if not path or parts.is_absolute() or '..' in parts.parts or '\\' in path or ':' in path or sensitive(path):
            raise ValueError('Declaration path must be a nonsensitive relative tracked file.')
        root = Path(repo).resolve()
        try:
            (root / path).resolve().relative_to(root)
        except ValueError:
            raise ValueError('Declaration path escapes the repository.') from None
        if path not in indexed or indexed[path][0] not in ('100644', '100755'):
            raise ValueError('Declaration source is missing or is not a tracked regular file.')
        line = item.get('line')
        if line is not None:
            if type(line) is not int or line < 1:
                raise ValueError('Declaration line must be a positive integer.')
            oid = indexed[path][1]
            if int(git(repo, 'cat-file', '-s', oid)) > MAX_BLOB:
                raise ValueError('Declaration source exceeds the inspection limit.')
            if line > len(git(repo, 'cat-file', 'blob', oid).splitlines()):
                raise ValueError('Declaration line is outside the indexed source.')
        commands = item.get('commands', [])
        if not isinstance(commands, list) or not all(isinstance(x, str) for x in commands):
            raise ValueError('Declaration commands must be an array of strings.')
        result.append({'topic': topic, 'path': path, 'line': line, 'blob': indexed[path][1],
                       'basis': 'maintainer_declaration_unverified', 'command_count': len(commands),
                       'commands_status': 'unverified_not_executed'})
    return result


def generate(repo, declaration=None):
    """Read tracked regular-file index blobs; never run target code or copy source text."""
    entries = git(repo, 'ls-files', '--stage', '-z').split(b'\0')
    evidence, excluded = [], {'sensitive_names': 0, 'nonregular': 0, 'oversized': 0, 'binary_or_invalid': 0}
    tracked = 0
    indexed = {}
    for entry in entries:
        if not entry:
            continue
        meta, raw_path = entry.split(b'\t', 1)
        mode, oid, stage = meta.decode('ascii').split()
        if stage != '0':
            raise ValueError('Unmerged index: resolve conflicts before generating a handover.')
        tracked += 1
        path = raw_path.decode('utf-8', errors='replace')
        indexed[path] = (mode, oid)
        if sensitive(path):
            excluded['sensitive_names'] += 1
            continue
        if mode not in ('100644', '100755'):
            excluded['nonregular'] += 1
            continue
        name = PurePosixPath(path).name.lower()
        categories = []
        if name in ('package.json', 'pyproject.toml', 'requirements.txt', 'setup.py', 'setup.cfg'):
            categories.append('dependency_manifest')
        if path.startswith('.github/workflows/'):
            categories.append('automation')
        if name in ('dockerfile', 'compose.yml', 'compose.yaml', 'docker-compose.yml', 'procfile'):
            categories.append('deployment_config')
        if name == 'codeowners':
            categories.append('ownership_config')
        for category in categories:
            evidence.append({'topic': category, 'path': path, 'blob': oid, 'line': None,
                             'basis': 'file_present'})
        if not name.endswith(('.md', '.rst', '.txt')) or name == 'requirements.txt':
            continue
        size = int(git(repo, 'cat-file', '-s', oid))
        if size > MAX_BLOB:
            excluded['oversized'] += 1
            continue
        raw = git(repo, 'cat-file', 'blob', oid)
        try:
            content = raw.decode('utf-8')
            if '\0' in content:
                raise UnicodeError()
        except UnicodeError:
            excluded['binary_or_invalid'] += 1
            continue
        seen = set()
        for number, line in enumerate(content.splitlines(), 1):
            for topic, pattern in TOPICS.items():
                if topic not in seen and pattern.search(line):
                    evidence.append({'topic': topic, 'path': path, 'blob': oid, 'line': number,
                                     'basis': 'keyword_location_not_verified_procedure'})
                    seen.add(topic)
    if declaration is not None:
        evidence.extend(validate_declaration(repo, declaration, indexed))
    evidence.sort(key=lambda e: (e['topic'], e['path'], e['line'] or 0))
    found = {e['topic'] for e in evidence}
    gaps = [{'topic': topic, 'status': 'unknown', 'question': question}
            for topic, question in {
                'setup': 'What is the tested first-run procedure?',
                'operations': 'Where are deploy, rollback and recovery procedures?',
                'ownership': 'Who accepts operational responsibility?',
                'testing': 'Which checks must pass before a handover?',
            }.items() if topic not in found]
    return {'schema_version': 1, 'snapshot': 'git_index', 'status': 'inventory_only',
            'commit': optional_git(repo, 'rev-parse', '--verify', 'HEAD'),
            'branch': optional_git(repo, 'symbolic-ref', '--quiet', '--short', 'HEAD'),
            'dirty': bool(git(repo, 'status', '--porcelain', '--untracked-files=normal', '--ignore-submodules=all')),
            'tracked_entries': tracked, 'excluded_counts': excluded, 'evidence': evidence,
            'open_questions': gaps,
            'limitations': ['No target commands executed; operational readiness is not verified.',
                            'Keyword locations may be mentions, negations or obsolete instructions.',
                            'Paths and blob identifiers can be sensitive; review before sharing.',
                            'Filename exclusions are not a comprehensive secret scanner.',
                            'Staged snapshot excludes unstaged changes and untracked files.']}


def markdown(report):
    lines = ['# Handoff Pack', '', 'Status: inventory only. Snapshot: Git index.', '',
             'Source contents, commands, remote URLs, author identities and environment values are omitted.', '',
             '## Evidence map', '']
    for item in report['evidence']:
        # JSON quoting prevents source-controlled filenames from becoming Markdown links or HTML.
        location = json.dumps(item['path'], ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('`', '\\u0060')
        lines.append(f"- {item['topic']}: `{location}` line {item['line'] or 'n/a'}; blob `{item['blob']}`; {item['basis']}")
    if not report['evidence']:
        lines.append('No recognized evidence locations.')
    lines += ['', '## Open questions', '']
    lines += [f"- Unknown: {q['question']}" for q in report['open_questions']]
    if not report['open_questions']:
        lines.append('Topic locations found; a human must still validate every procedure and owner.')
    lines += ['', '## Limits', ''] + ['- ' + x for x in report['limitations']]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo', type=Path)
    parser.add_argument('--format', choices=('json', 'markdown'), default='markdown')
    parser.add_argument('--declaration', type=Path, help='Optional local JSON handover declarations; commands never run')
    parser.add_argument('--output', type=Path, help='Write a new report file; refuse to overwrite any existing path')
    args = parser.parse_args(argv)
    try:
        declaration = json.loads(args.declaration.read_text(encoding='utf-8')) if args.declaration else None
        report = generate(args.repo, declaration)
        rendered = json.dumps(report, indent=2) + '\n' if args.format == 'json' else markdown(report)
        if args.output:
            with args.output.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(rendered)
        else:
            print(rendered, end='')
    except (ValueError, OSError) as exc:
        print('handoff-pack: ' + str(exc), file=sys.stderr)
        return 2
    return 1 if report['open_questions'] else 0


if __name__ == '__main__':
    sys.exit(main())

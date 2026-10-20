# Handoff Pack

**A repository is not a handover. Find the missing operational answers before the next person inherits it.**

Handoff Pack builds a source-linked operational evidence map from a local Git index. It points to setup, tests, ownership, recovery, dependency manifests and automation, then turns missing documentation signals into concrete questions. It never executes project scripts or emits their contents.

Useful for agency handovers, maintainer transitions and projects built with coding assistants. Unlike a broad repository summary, its output is deliberately small: review locations, exact source blob identifiers, line numbers and explicit unknowns. It cannot prove a service can be operated.

## Quick start

Requires Python 3.9+ and Git on PATH; no Python packages, network or paid API required.

```sh
python scripts/handoff_pack.py /path/to/repository
python scripts/handoff_pack.py /path/to/repository --format json --output handoff.json
python -m unittest discover -s tests -v
```

Run from this downloaded repository, or use an absolute path to the script. Reports go to stdout unless `--output` names a new report file. That option uses exclusive creation and refuses to overwrite any existing path, with exit 2. Keep report files outside the target repository; target source files are never changed. Exit 0 means every topic has an evidence location, **not operational readiness**. Exit 1 means open questions remain; exit 2 means invalid input, output conflict, or an inaccessible repository/index.

The tool inspects tracked documentation contents for keywords. Its output omits those contents; “metadata” describes the report, not a promise that source documents are never read.

Reports also identify the current commit, branch (null for detached HEAD), and whether the repository has working or staged changes. An unborn repository has no commit. Branch names and source paths may be private.

For precise maintainer-supplied source pointers, pass `--declaration examples/handoff.json`. Each declaration must reference a tracked regular file within the repository, with an optional valid line number. Listed commands are counted, never printed or executed. Declarations remain explicitly unverified.

## Before and after

Before: “The source is all there; someone can work out the deployment.”

After: a report points to `README.md:3` for setup and `README.md:6` for testing, records the exact indexed blob, and asks “Where are deploy, rollback and recovery procedures?” and “Who accepts operational responsibility?” No owner or working deployment is invented.

Try the synthetic example in a new temporary directory you choose:

```sh
git init /path/to/toy-handoff
# Copy the two files from examples/toy-service into that directory.
git -C /path/to/toy-handoff add README.md package.json
python scripts/handoff_pack.py /path/to/toy-handoff --format json
```

No commit, account access or dependency installation is needed. The index is the source: stage changes deliberately in your own repository if you want them included. The tool never stages for you.

## Install as a Claude Code skill

Copy this repository's `SKILL.md`, `scripts/` and `references/` into `~/.claude/skills/handoff-pack/` for personal use, or `.claude/skills/handoff-pack/` in a project. Then explicitly invoke:

```text
/handoff-pack /path/to/repository
```

`disable-model-invocation: true` keeps this user-invoked. The portable Python CLI can be used without Claude. Other assistants can run the CLI, but their native skill loaders are not claimed to be compatible.

## Boundaries

- Reads staged regular-file blobs, not untracked files or unstaged edits. Git conflicts block generation. Symlinks and submodules are skipped.
- Emits source paths, blob IDs and keyword locations, not contents, commands, remote URLs, authors or environment values.
- Sensitive filename exclusions are a limited precaution, **not a comprehensive secret scanner**. Paths and identifiers may themselves be private: review before sharing.
- A word such as “deployment” can appear in a negation or obsolete document. Matches are locations to review, never proof. File presence also does not validate configuration.
- UTF-8 text documents only, up to 1 MiB each. No deep code analysis, dependency checks, runtime verification or security sandbox.
- An agent expanding the report into a content-bearing handover must separately respect source authorization and data sensitivity.

See [the evidence contract](references/evidence.md) for schema and interpretation. Tests create only disposable synthetic Git repositories and check snapshot integrity, secret-content omission, no target execution, excluded files, and evidence semantics.

## Licensing

MIT, see [LICENSE](LICENSE).

---

Built by Kamesh Jindal at [OMX Digital](https://omxdigital.ai). Part of the [OMX Claude Skills toolkit](https://github.com/OmxKamesh/claude-code-skills). Need this set up for your business? [kamesh@omxdigital.ai](mailto:kamesh@omxdigital.ai)

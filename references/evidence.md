# Evidence contract

The report uses schema_version 1. `snapshot: git_index` identifies the staged snapshot; each evidence item carries its Git blob object ID. The helper reads blobs by ID, so a working-tree file cannot silently replace the cited content. Concurrent index edits are outside the snapshot captured by the initial listing.

Commit, branch and dirty-state metadata are read after the index inventory and may change concurrently. They are context, not an atomic Git snapshot. Null commit means an unborn repository; null branch indicates detached HEAD. The CLI never reads remote configuration.

Optional declarations use `{"procedures":[{"topic":"operations","path":"docs/ops.md","line":3,"commands":["example command"]}]}`. Topic must be setup, operations, ownership or testing. Only relative, tracked regular-file paths are accepted; traversal, escaping symlinks, sensitive filenames and invalid lines are rejected. Commands are counted but never emitted or executed. The source pointer does not prove the declaration true. Its basis stays `maintainer_declaration_unverified`.

`file_present` means a recognized manifest, deployment file, workflow or CODEOWNERS path exists in the index. It says nothing about its validity. `keyword_location_not_verified_procedure` identifies the first matching line per topic in a UTF-8 Markdown, RST or text file. Negations and stale documentation can match. Missing matches generate open questions, not accusations that a capability is absent. Present matches as **locations to review**.

The helper does not emit file contents, script commands, Git remote URLs, commit authors, environment values or raw Git error output. It excludes likely sensitive filenames, symlinks and submodules. Documentation larger than 1 MiB and non-UTF-8/binary documents are skipped. Excluded paths are not printed; only aggregate counts are included.

Paths themselves can contain private names or secrets. Blob IDs can identify source versions. This is a data-minimizing inventory, not a security sandbox or comprehensive scanner. Keep reports local until reviewed. Index conflicts stop the report with exit 2. Empty indexes produce an empty inventory with unknowns.

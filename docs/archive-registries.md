# Archive registries

`ledger.archive_registry_paths` is an optional list of distinct safe repository-relative
registry files, defaulting to empty. All declared files use the existing strict parser.
Missing files, corrupt rows, duplicate IDs/aliases and ID/alias collisions fail closed.

`EntityRegistry.load_configured(root, config)` reads the union for lookup, search, relation
validation, reference/naming/legacy checks and allocation. `rows` contains the union,
`main_rows` the primary rows, and `sources[id]` the actual diagnostic path. The single-file
`load(path, config)` API remains available. Allocation re-reads all tables under the existing
main-worktree lock and uses both the archived serial maximum and local high-water marks.
Allocation and update save only primary rows; archived updates return `ERR_ARCHIVE_READONLY`.
This interface does not move rows or approve retirement.

The index renders primary rows only. If the DECISION vocabulary contains ACTIVE, only ACTIVE
decisions receive full blocks; DORMANT receives a separate ID/name list, while DRAFT/RETIRED
remain queryable. Existing vocabularies retain their behavior. A live prose reference to a
hidden entity returns `ERR_INDEX_HIDDEN_REFERENCE`: the writer must explicitly rewrite live
wording, rather than having the renderer silently rewrite facts. All relations still validate
against the issuance union. Archive anchors and statuses remain subject to existing checks;
archive tables are structurally parsed instead of scanned as prose, just like the primary.

Development evidence: archive semantic tests 9 passed, core CLI 8 passed, update 15 passed,
integrity 58 passed. Index tests had 45 passed and 2 unchanged fixtures failed at symbolic-link
creation with Windows WinError 1314. This is partial verification, not an all-green suite.
Index-check tests had 15 passed and 2 further symbolic-link fixture failures for the same reason.
The same archive tests against source commit `651009c72ec650bdfdceebfef361c2ab2aed6862`
produced 5 failed/4 passed because the old config rejects archive paths and cannot satisfy
archive lookup/check/allocation or the activation view.

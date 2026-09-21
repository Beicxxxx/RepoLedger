# Agents Instructions — RepoLedger

Canonical instructions for all coding harnesses. Keep this file <= 65 lines.

## Scope
- RepoLedger CLI, its own Skill, tests, examples and documentation only.
- cross-harness-sync is an independent optional partner; do not vendor or modify it.
- Python 3.11+, standard library first, tomllib, Git-native text storage.
- No remote creation, publication, global plugin installation or old-project migration without a new request.

## Session start
1. Inspect git status; preserve unrelated user changes.
2. Read docs/rfc-architecture.md.
3. Inspect relevant issues/tests. No remote issue tracker is assumed.

## Invariants
- TYPE-N: uppercase type, no zero padding, per-type monotonic, append-only.
- Gaps are allowed by default; never recycle or renumber issued entities.
- Require a physical anchor by default; proposals are valid evidence carriers.
- anchor means evidence, not assignee; existence does not prove completion.
- Strict schema/table parsing; never skip corrupt records.
- check is read-only and must not auto-register unknown references.
- Stable diagnostic codes with locations and actionable next steps.
- Worktree, index and commit-tree are different views; reject unsupported views.
- Allocation only in the authoritative main worktree under its short lock.
- Lookup before referencing or allocating; keep Skill rules delegated to CLI.
- Do not claim verified historical metrics, publication or semantic-drift prevention.

## Validation
Before committing, run python -m pytest -v and require all tests green.
Sandboxed Windows runs may use a fresh --basetemp below .test-runs
and -p no:cacheprovider if the default temporary/cache directories are inaccessible.
Never commit secrets or credentials.
Use imperative commit messages: feat:, fix:, docs:.

# Agents Instructions — RepoLedger

Canonical instructions for ALL harnesses (Claude Code, Antigravity, Codex, Kimi, etc.).
`CLAUDE.md` is a pointer to this file. Keep this file <= 65 lines.

## Project Scope
RepoLedger: Git-native Entity & Knowledge Governance for AI Coding Agents.
- Zero external database, pure text, Git-native.
- Python 3.11+, stdlib priority, tomllib for ledger.toml.
- Two independent packaged skills: `repo-ledger` and `cross-harness-sync`.

## On Session Start — the ONLY required reads
1. `git status` (clean working directory).
2. `docs/rfc-architecture.md` (architecture invariants and boundaries).
3. Active issues / tests.

## Development Constraints
- Python 3.11+ standard library first. No heavy external frameworks.
- Entity IDs: `TYPE-N` (uppercase, no zero padding, monotonic per type, append-only).
- Serial gaps are NOT errors by default (`allow_gaps = true`).
- Physical anchor (`anchor`) required by default; exploration tasks anchor to proposal docs.
- `check` command is strictly read-only; never auto-register unknown entities.
- Error codes must be stable (`ERR_UNREGISTERED_ENTITY`, `ERR_INVALID_STATUS`, etc.).
- Both CLI and skills must remain independent without circular hard coupling.

## Testing & Quality Gate
- Before committing any change, run:
  ```bash
  python -m pytest -v
  ```
  All tests must pass 100% green.
- Never commit secrets or credentials (`.env`).
- Commit messages: imperative present tense (`feat: ...`, `fix: ...`, `docs: ...`).

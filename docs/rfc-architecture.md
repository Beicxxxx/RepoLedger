# RepoLedger Architecture & First-Release Scope (RFC)

## 1. Background & Heritage

RepoLedger originates from two battle-tested practices developed during complex multi-agent coding sessions:
1. **cross-harness-sync**: A Git-and-Markdown protocol to transfer progress, blockers, and next prompts across different AI agents, sessions, and machines.
2. **Entity Numbering System**: Stable identifiers (`TYPE-N`), a single-source-of-truth markdown ledger, and static inverse reference linter to eliminate duplicate creation, dangling references, and code drift.

We promise entity referential integrity and traceability; we do not claim to have magically solved all semantic drift.

---

## 2. Fixed Constraints (已确定约束)

1. **Git-Native & Pure Text**: Zero external databases (no SQLite, no Postgres, no cloud backend). All data resides in diffable, Git-tracked text files.
2. **Minimal Tech Stack**: Python 3.11+, prioritizing the standard library. Uses built-in `tomllib` to read `ledger.toml`.
3. **Canonical Identifier Format**: `TYPE-N` (uppercase type name, no leading zeros, monotonically increasing serial per type, append-only, never reused, never reordered).
4. **Serial Gaps are Not Errors**: Unlike rigid consecutive sequences, serial gaps are allowed by default (`allow_gaps = true`), recognizing that exploratory drafts or dropped proposals naturally leave numbers retired.
5. **Authoritative Markdown Ledger**: The structured markdown table (e.g. `.ledger/ENTITY_REGISTRY.md`) is the single authoritative data source. It must declare an explicit schema version (e.g. `<!-- schema: 1.0 -->`); parser errors fail loud.
6. **Minimal Default Entity Types**: `TASK`, `DECISION`, `ISSUE`. Projects can configure custom types in `ledger.toml`.
7. **Physical Grounding (`anchor`)**: Entities are grounded via an `anchor` (tracked file path, `commit:path`, or commit SHA). Exploratory tasks can anchor to real proposal documents. File existence does not imply task completion.
8. **Single Allocation Workspace & Short Lock**: Allocations occur in an authoritative workspace protected by a file lock and atomic file replacement during the read -> allocate -> write cycle.
9. **Strictly Read-Only Linter (`check`)**: The linter never automatically registers unknown entities to silence errors. It outputs stable error codes, location, entity name, reason, actionable suggestions, and supports JSON output.
10. **Pre-Commit Hook as Local Feedback**: Local hooks provide fast feedback, while CI remains the mandatory enforcement gateway. Hook installation must refuse to overwrite existing hooks without explicit `--force`.

---

## 3. Implementation Choices (首版实现选择)

1. **Relation Model**: Single-value `parent` (hierarchical tree) and multi-value `supersedes` (comma/semicolon separated).
2. **CLI Commands**:
   - `repo-ledger init`: Scaffolds `ledger.toml` and `.ledger/ENTITY_REGISTRY.md`.
   - `repo-ledger allocate <TYPE> <NAME> [--anchor <PATH>]`: Atomically allocates the next ID.
   - `repo-ledger lookup <ID> [--json]`: Queries an entity's metadata without reading the entire ledger.
   - `repo-ledger check [--json] [--root <DIR>]`: Statically scans code and markdown for unregistered entity references.
   - `repo-ledger tree`: Visualizes parent/child hierarchy.
   - `repo-ledger hook install [--force]`: Installs non-destructive git pre-commit hook.
3. **Scanning Scope**: Scans text files matching configured extensions (`.py`, `.ts`, `.js`, `.go`, `.rs`, `.json`, `.md`), respecting ignore globs.

---

## 4. Deferred Items (后置事项)

1. **MCP (Model Context Protocol) Server**: Deferred to V2. V1 focuses strictly on deterministic CLI and skills.
2. **Generic Directed Acyclic Graph (DAG)**: Multi-parent `derived_from` or general graph traversal engines are deferred until real workflows demand them.
3. **Distributed Allocation / Multi-Clone Locks**: Cross-machine lock arbitration is out of scope for V1.
4. **State Transition History Audit**: Historical state transition matrix enforcement is deferred to post-V1.

---

## 5. Integration Boundaries: RepoLedger vs. Cross-Harness-Sync

* **RepoLedger**: Manages entity identity, status, physical anchors, relationships, and referential integrity.
* **cross-harness-sync**: Manages narrative context, active focus, session handoff prompt (`NEXT_PROMPT.md`), and single-writer relay.
* **Touchpoints**:
  - `cross-harness-sync` references canonical IDs (`TASK-1`, `ISSUE-2`) in `CURRENT.md`.
  - On session start, agents run `repo-ledger lookup <TASK-ID>` to read the active anchor, avoiding context bloat from reading the full ledger.
  - `sync_verify.py` invokes `repo-ledger check` in its `extra_checks` pipeline.
  - The two skills do not hard-depend on each other; either can be used standalone.

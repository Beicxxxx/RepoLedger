# RepoLedger 📜

> **Git-native Entity & Knowledge Governance for AI Coding Agent Swarms.**  
> Stop AI agents from hallucinating task numbers, drifting terminology, and inventing ungrounded dependencies.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-brightgreen.svg)](https://python.org)
[![Tests: Passing](https://img.shields.io/badge/tests-100%25%20passed-success.svg)](#)

---

## 💡 Why RepoLedger?

When AI coding assistants (Claude Code, Antigravity, Cursor, Codex) collaborate on projects across weeks and hundreds of commits, they inevitably suffer from:
1. **Semantic Drift**: Creating inconsistent aliases (`B1.5`, `S1-b`, `Task 5`) that mutate across sessions.
2. **Dangling References**: Claiming in docstrings or comments that a feature satisfies `TASK-99` when no such task exists.
3. **Context Bloat**: Feeding megabytes of chat logs just so the incoming agent knows what is done and what is pending.

**RepoLedger** provides a **zero-dependency, Git-native, fail-closed** entity registry and static linter that guarantees 100% referential integrity across your entire codebase.

---

## ⚡ Quickstart

### 1. Installation

```bash
pip install repo-ledger
# or with uv:
uv add --dev repo-ledger
```

### 2. Initialize in your Repository

```bash
repo-ledger init
```
This generates:
* `ledger.toml`: Configurable entity types (`TASK`, `DECISION`, `EXP`, `ISSUE`, `GATE`).
* `.ledger/ENTITY_REGISTRY.md`: The single source of truth markdown ledger.

### 3. Allocate an Entity

```bash
repo-ledger allocate TASK "Implement auth rate limiter" --owner src/auth/limiter.py --status IN_PROGRESS
```
Output:
```
[repo-ledger] Allocated: TASK-1 - Implement auth rate limiter (IN_PROGRESS)
             Registry updated: .ledger/ENTITY_REGISTRY.md
```

### 4. Verify Codebase Invariants (Fail-Closed)

```bash
repo-ledger check
```
If an agent writes `# Implements TASK-99` in any `.py`, `.ts`, or `.md` file without registering it, `repo-ledger` fails immediately:
```
[repo-ledger] FAILED with 1 issue(s):
  ERROR: src/worker.py:42: references unregistered entity 'TASK-99'
```

### 5. Visualize Hierarchy

```bash
repo-ledger tree
```
Output:
```
Entity Hierarchy (4 entities):
|-- TASK-1 [DONE] Root Infrastructure
|   |-- TASK-2 [DONE] Database Schema
|   `-- TASK-3 [IN_PROGRESS] API Gateway
`-- DECISION-1 [IN_FORCE] Migrate to PostgreSQL
```

### 6. Install Git Hook

```bash
repo-ledger hook install
```
Ensures no dangling or corrupted entity references can ever be committed.

---

## ⚙️ Configuration (`ledger.toml`)

Customize entity types, allowed statuses, and scanned paths:

```toml
[ledger]
registry_path = ".ledger/ENTITY_REGISTRY.md"
code_extensions = [".py", ".ts", ".js", ".go", ".rs", ".json"]
ignore_globs = ["node_modules/**", "dist/**", ".git/**"]

[types.TASK]
prefix = "TASK"
allowed_statuses = ["BACKLOG", "IN_PROGRESS", "BLOCKED", "DONE", "DROPPED"]
require_owner = true

[types.DECISION]
prefix = "DECISION"
allowed_statuses = ["DRAFT", "IN_FORCE", "SUPERSEDED"]
require_owner = true
```

---

## 🤖 AI Agent Integration (Antigravity & Claude Code)

Add a rule to your `AGENTS.md` or `CLAUDE.md`:
```markdown
## Entity Discipline
- Every task, decision, and experiment must be formally allocated: `repo-ledger allocate <TYPE> <NAME> --owner <PATH>`.
- Before committing, always verify with `repo-ledger check`.
- Never invent unnumbered shorthand identifiers in code or prose.
```

---

## 📄 License

MIT License © 2026 Beichen

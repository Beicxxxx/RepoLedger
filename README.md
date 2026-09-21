# RepoLedger 📜

> **Git-native Entity & Knowledge Governance for AI Coding Agents.**  
> Grounded task/decision identity, authoritative markdown ledger, and fail-closed reference linter.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11+-brightgreen.svg)](https://python.org)
[![Tests: Passing](https://img.shields.io/badge/tests-100%25%20passed-success.svg)](#)

---

## 💡 What is RepoLedger?

When AI coding assistants (Claude Code, Antigravity, Cursor, Codex) collaborate across multiple sessions, machines, and weeks, tasks and decisions easily suffer from:
1. **Dangling References**: Claiming in code comments, docstrings, or handoffs that work resolves an unregistered or hallucinated task ID.
2. **Ungrounded Statuses**: Tasks marked "DONE" without an authoritative physical artifact to prove it.
3. **Context Inflation**: Feeding megabytes of historical chat logs to incoming agents just to convey current project status.

**RepoLedger** provides a **zero-dependency, Git-native, fail-closed** entity registry and static reference linter. We promise strict **referential integrity and physical traceability**.

---

## 📦 Package & Skills Structure

RepoLedger is organized as a single open-source repository containing a core Python CLI and two standalone, mutually compatible AI agent skills:

* **Core Engine & CLI (`repo-ledger`)**: The deterministic Python CLI managing allocation, lookup, and static reference scanning.
* **Skill 1: `repo-ledger` (`skills/repo-ledger/`)**: Teaches AI agents how to lookup active task anchors, allocate canonical IDs, and verify referential integrity.
* **Skill 2: `cross-harness-sync` (`skills/cross-harness-sync/`)**: A zero-daemon Git-and-Markdown relay protocol managing multi-agent session handoffs (`CURRENT.md` + `NEXT_PROMPT.md`) and single-writer coordination.

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
* `ledger.toml`: Configurable entity types (`TASK`, `DECISION`, `ISSUE`), allowed statuses, and scanned extensions.
* `.ledger/ENTITY_REGISTRY.md`: The authoritative structured markdown ledger (with schema versioning).

### 3. Allocate an Entity

```bash
repo-ledger allocate TASK "Implement rate limiting" --anchor src/limiter.py --status IN_PROGRESS
```
Output:
```
[repo-ledger] Allocated: TASK-1 - Implement rate limiting (IN_PROGRESS)
             Anchor: src/limiter.py
             Registry updated: .ledger/ENTITY_REGISTRY.md
```

### 4. Query Entity Metadata (`lookup`)

```bash
repo-ledger lookup TASK-1 --json
```

### 5. Statically Verify References (`check`)

```bash
repo-ledger check
# or structured JSON output:
repo-ledger check --json
```
If an agent writes `# Implements TASK-99` in any tracked code or doc file without registering it, `repo-ledger` fails immediately with a stable error code and actionable suggestion:
```
[ERR_UNREGISTERED_ENTITY] src/worker.py:42: References unregistered entity 'TASK-99' (Suggestion: Allocate TASK-99 via `repo-ledger allocate TASK ...` or fix typo)
```

### 6. Visualize Hierarchy (`tree`)

```bash
repo-ledger tree
```

### 7. Non-Destructive Git Hook (`hook install`)

```bash
repo-ledger hook install
```
Installs a non-destructive `.git/hooks/pre-commit` hook that runs `repo-ledger check` before commits.

---

## ⚙️ Configuration (`ledger.toml`)

```toml
[ledger]
schema_version = "1.0"
registry_path = ".ledger/ENTITY_REGISTRY.md"
allow_gaps = true
doc_dirs = ["docs", ".ai/state", ".ai/handoff"]
code_extensions = [".py", ".ts", ".js", ".go", ".rs", ".json"]
ignore_globs = [
    "node_modules/**", "dist/**", "build/**", ".git/**", "tests/fixtures/**"
]

[types.TASK]
prefix = "TASK"
allowed_statuses = ["BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE", "DROPPED"]
require_anchor = true
description = "Actionable engineering or research tasks"

[types.DECISION]
prefix = "DECISION"
allowed_statuses = ["DRAFT", "IN_FORCE", "SUPERSEDED"]
require_anchor = true
description = "Architecture Decision Records and policy rulings"

[types.ISSUE]
prefix = "ISSUE"
allowed_statuses = ["OPEN", "INVESTIGATING", "RESOLVED", "WONT_FIX"]
require_anchor = true
description = "Defects, regressions, and blockers"
```

---

## 📄 License

MIT License © 2026 Beichen

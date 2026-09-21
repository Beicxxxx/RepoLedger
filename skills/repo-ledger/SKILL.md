---
name: repo-ledger
description: Operate the Git-native RepoLedger entity registry and static linter. Allocate canonical IDs (TASK-N, DECISION-N, ISSUE-N), lookup entity status and physical anchors, and run fail-closed reference checks. Use when the user mentions entity IDs, task allocation, ADRs, or before committing code to ensure zero unregistered entity references.
---

# RepoLedger Skill

Authoritative entity governance for AI agents working in this repository.

## Guiding Principles for Agents

1. **Never invent shorthand or arbitrary codes** (e.g. do not write `Task 1.2`, `M0`, `B1.5`).
2. **Always query before allocating**: run `repo-ledger lookup <ID>` to inspect status and anchor.
3. **Always ground allocations**: when allocating a new entity, always specify `--anchor <PATH>` pointing to a real file, proposal doc, or commit hash.
4. **Fail-Closed Verification**: before every commit or task completion, run `repo-ledger check`. Fix any unregistered references before proceeding.

## Daily Agent Commands

### 1. Lookup Current Entity
Before starting work on an assigned task:
```bash
repo-ledger lookup TASK-1 --json
```
Reads the title, status, parent, and authoritative artifact anchor.

### 2. Allocate a New Entity
When creating a new task, decision, or logging an issue:
```bash
repo-ledger allocate TASK "Implement rate limiting" --anchor src/limiter.py --status IN_PROGRESS
repo-ledger allocate DECISION "Adopt SQLite for local cache" --anchor docs/adr-001.md --status IN_FORCE
repo-ledger allocate ISSUE "Memory leak in background loop" --anchor tests/test_leak.py --status OPEN
```

### 3. Verify Codebase Referential Integrity
```bash
repo-ledger check
# Or structured output:
repo-ledger check --json
```
If an unregistered entity (e.g. `TASK-99`) is mentioned in any `.py`, `.ts`, `.rs`, or `.md` file, this command fails and returns the exact `file:line` for immediate self-healing.

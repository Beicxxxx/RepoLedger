---
name: cross-harness-sync
description: Operate a Git+Markdown shared-state relay protocol across AI coding harnesses (Claude Code, Antigravity, Codex, Kimi, etc.) and developer machines. Uses an .ai/ directory (CURRENT.md runtime state, NEXT_PROMPT.md handoff, advisory writer lock, sync_verify check). Use when managing multi-agent handoffs, session continuity, or cross-harness state sharing.
---

# Cross-Harness Sync

A zero-infrastructure protocol for sharing narrative work state across AI coding harnesses and developer machines: plain Markdown in `.ai/`, Git as the transport, and verification scripts as enforcement.

## Architecture

* **Runtime State**: `.ai/state/CURRENT.md` (sole runtime state file, $\le 80$ lines).
* **Handoff**: `.ai/handoff/NEXT_PROMPT.md` (self-contained next prompt, overwritten each stage).
* **Decision History**: `.ai/state/LEDGER.md` (single-line append-only decision record).
* **Advisory Lock**: `.ai/runtime/WRITER_LOCK.json` (single-writer coordination; not distributed mutual exclusion).
* **Verification**: `.ai/scripts/sync_verify.py` (checks budgets, secrets, and project extra checks).

## Daily Workflow for Agents

### 1. On Session Start
1. `git pull --ff-only` (the remote is shared memory).
2. Read `.ai/state/CURRENT.md` (active task, status, constraints).
3. Read `.ai/handoff/NEXT_PROMPT.md` (your specific task instructions).
4. Shortcut: `python .ai/scripts/checkpoint.py --prime`.

### 2. Before Writing State
Acquire the advisory writer lock:
```bash
python .ai/scripts/checkpoint.py --lock --agent <harness-name> --reason <task-id>
```
If an active unexpired lock is held by another agent, STOP and report.

### 3. Integration with RepoLedger
* Tasks and issues referenced in `CURRENT.md` and `NEXT_PROMPT.md` must use canonical `TYPE-N` IDs.
* When starting a task, run `repo-ledger lookup <TASK-ID>` to read the authoritative anchor.
* `sync_verify.py` runs `repo-ledger check` in `extra_checks` to ensure zero broken entity references before handoff.

### 4. Close-Out
1. Run `python .ai/scripts/sync_verify.py` (must be 100% green).
2. Update `.ai/state/CURRENT.md` and `.ai/handoff/NEXT_PROMPT.md`.
3. Release writer lock: `python .ai/scripts/checkpoint.py --unlock --agent <harness-name>`.
4. Commit and push.

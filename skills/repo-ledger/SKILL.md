---
name: repo-ledger
description: Query and allocate RepoLedger entities and diagnose reference integrity errors in repositories using ledger.toml.
---

# RepoLedger

Follow the repository's AGENTS.md and the CLI configuration.

1. Before referencing an ID, run `repo-ledger lookup <ID> --json`. Before creating an entity, inspect relevant existing references and query plausible matches; lightweight title search is not implemented yet.
2. Allocate genuinely new entities with `repo-ledger allocate <TYPE> "<title>" --anchor <tracked-file>`. Use the returned ID; never predict a number. Mint only in the designated main workspace.
3. Read the single entity and its anchor as needed. Do not preload the whole registry.
4. Update an existing row's status/note only from explicit evidence and run `repo-ledger check --json`. Preserve ID, order and historical records. No update command or transition/evidence enforcement exists yet.
5. On failure, inspect the reported location. For unknown references, lookup first, determine typo versus new entity, then correct or explicitly allocate. Never fabricate registration or widen ignores to make checks green.

Deterministic schema, statuses, relations and anchor rules belong to CLI/configuration, not another rule set in this Skill. Current check validates the working tree only; do not present it as staged or CI merge validation. Historical anchors are currently unsupported.

cross-harness-sync is optional and independently installed. RepoLedger does not manage git pull/push, handoff documents, approval roles or session-wide writer policies.

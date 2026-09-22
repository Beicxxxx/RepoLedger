---
name: repo-ledger
description: Query and allocate RepoLedger entities and diagnose reference integrity errors in repositories using ledger.toml.
---

# RepoLedger

Follow the repository's AGENTS.md and the CLI configuration.

1. Before referencing an ID, run `repo-ledger lookup <ID> --json`. The argument may be a current ID or a registered `legacy` alias; if it is old, use the returned current ID in all new prose. Before creating an entity, inspect relevant existing references and query plausible matches; lightweight title search is not implemented yet.
2. Allocate genuinely new entities with `repo-ledger allocate <TYPE> "<title>" --anchor <tracked-file>`. Use the returned ID; never predict a number. A `--legacy` value is only for registering a documented pre-existing alias and is never a new spelling to write. Mint only in the designated main workspace.
3. Read the single entity and its anchor as needed. Do not preload the whole registry. Treat legacy aliases as read-only historical evidence; do not reassign or recycle them.
4. Update an existing row's status/note only from explicit evidence and run `repo-ledger check --json`. Preserve ID, order and historical records. Run `repo-ledger check-legacy --json` when importing or reviewing frozen text; `check` already aggregates this guard.
5. On failure, inspect the reported location. For unknown references, lookup first, determine typo versus new entity, then correct or explicitly allocate. Never fabricate registration, use a shape regex for retired codes, or widen ignores/exemptions to make checks green.
6. Drafts, task briefs and reviews do not mint IDs. Allocate only when the landing change can append the registry row and use the returned ID in the same committed change. A short allocation lock protects one mint operation; it is not cross-clone uniqueness proof.

Deterministic schema, statuses, relations, anchor rules and guard scope belong to CLI/configuration, not another rule set in this Skill. Current check validates the working tree only; do not present it as staged or CI merge validation. Historical anchors are currently unsupported. The only accepted spelling equivalence is `TYPE_N` in code identifiers/JSON keys to `TYPE-N`; ordinary prose uses `TYPE-N`, and this release does not claim a shared consumer helper.

cross-harness-sync is optional and independently installed. RepoLedger does not manage git pull/push, handoff documents, approval roles or session-wide writer policies.

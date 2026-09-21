"""Static linter for registry consistency and inverse reference scanning."""
from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import LedgerConfig
from .registry import EntityRegistry

HASH40_RE = re.compile(r"^[0-9a-f]{40}$")
COMMIT_PATH_RE = re.compile(r"^commit:([0-9a-f]{7,40})(:.+)?$")


@dataclass
class LintIssue:
    code: str
    location: str
    entity: str
    reason: str
    suggestion: str
    severity: str = "ERROR"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "location": self.location,
            "entity": self.entity,
            "reason": self.reason,
            "suggestion": self.suggestion,
        }

    def __str__(self) -> str:
        return f"[{self.code}] {self.location}: {self.reason} (Suggestion: {self.suggestion})"


def is_ignored(rel_path: str, ignore_globs: list[str]) -> bool:
    for pat in ignore_globs:
        if fnmatch.fnmatch(rel_path, pat) or fnmatch.fnmatch(Path(rel_path).name, pat):
            return True
        parts = rel_path.split("/")
        for i in range(1, len(parts)):
            sub = "/".join(parts[:i])
            if fnmatch.fnmatch(sub, pat) or fnmatch.fnmatch(sub + "/**", pat):
                return True
    return False


def check_registry_invariants(registry: EntityRegistry, root: Path) -> list[LintIssue]:
    issues: list[LintIssue] = []
    cfg = registry.config

    type_regex = re.compile(r"^([A-Z_]+)-([1-9][0-9]*)$")
    ids_seen: dict[str, int] = {}
    serials_per_type: dict[str, list[int]] = {}

    all_registered_ids = {r.id for r in registry.rows}

    for row_num, row in enumerate(registry.rows, start=1):
        rid = row.id.strip()
        m = type_regex.match(rid)
        if not m:
            issues.append(LintIssue(
                code="ERR_INVALID_ID_FORMAT",
                location=f"registry row {row_num}",
                entity=rid,
                reason=f"ID does not match canonical TYPE-N format (uppercase, no leading zero)",
                suggestion="Rename to TYPE-N, e.g. TASK-1",
            ))
            continue

        type_name, serial = m.group(1), int(m.group(2))
        ids_seen[rid] = ids_seen.get(rid, 0) + 1
        serials_per_type.setdefault(type_name, []).append(serial)

        # Status validation
        t_cfg = cfg.types.get(type_name)
        if t_cfg and t_cfg.allowed_statuses:
            if row.status not in t_cfg.allowed_statuses:
                issues.append(LintIssue(
                    code="ERR_INVALID_STATUS",
                    location=f"registry:{rid}",
                    entity=rid,
                    reason=f"Status {row.status!r} not in declared allowed vocabulary: {t_cfg.allowed_statuses}",
                    suggestion=f"Update status to one of {t_cfg.allowed_statuses}",
                ))

        # Parent existence
        if row.parent and row.parent not in all_registered_ids:
            issues.append(LintIssue(
                code="ERR_PARENT_NOT_FOUND",
                location=f"registry:{rid}",
                entity=rid,
                reason=f"Parent entity {row.parent!r} is not registered in the ledger",
                suggestion=f"Register parent {row.parent} first or correct parent field",
            ))

        # Supersedes existence (supports semicolon-separated list of superseded IDs)
        if row.supersedes:
            for s_id in (s.strip() for s in re.split(r"[,;]", row.supersedes) if s.strip()):
                if s_id not in all_registered_ids:
                    issues.append(LintIssue(
                        code="ERR_SUPERSEDES_NOT_FOUND",
                        location=f"registry:{rid}",
                        entity=rid,
                        reason=f"Superseded entity {s_id!r} is not registered in the ledger",
                        suggestion=f"Register {s_id} or correct supersedes field",
                    ))

        # Anchor validation (Grounding)
        if t_cfg and t_cfg.require_anchor:
            anchor = row.anchor.strip()
            if not anchor:
                issues.append(LintIssue(
                    code="ERR_MISSING_ANCHOR",
                    location=f"registry:{rid}",
                    entity=rid,
                    reason="Entity requires a physical anchor, but anchor field is empty",
                    suggestion="Set anchor to a tracked file path or commit hash",
                ))
            else:
                # Validate anchor target format and existence
                is_commit = bool(HASH40_RE.match(anchor) or COMMIT_PATH_RE.match(anchor))
                if not is_commit:
                    anchor_path = root / anchor
                    if not anchor_path.exists():
                        issues.append(LintIssue(
                            code="ERR_ANCHOR_NOT_FOUND",
                            location=f"registry:{rid}",
                            entity=rid,
                            reason=f"Physical anchor {anchor!r} does not exist on filesystem",
                            suggestion=f"Ensure {anchor} exists or update to an existing artifact",
                        ))

    # Duplicate ID check
    for rid, count in ids_seen.items():
        if count > 1:
            issues.append(LintIssue(
                code="ERR_DUPLICATE_ID",
                location=f"registry",
                entity=rid,
                reason=f"Entity ID {rid} is duplicated {count} times (must be strictly unique)",
                suggestion="Keep only one authoritative entry for this ID",
            ))

    # Optional Serial Gap Check (Only if allow_gaps is False)
    if not cfg.allow_gaps:
        for type_name, serials in serials_per_type.items():
            s_set = set(serials)
            max_s = max(s_set)
            expected = set(range(1, max_s + 1))
            missing = sorted(expected - s_set)
            if missing:
                issues.append(LintIssue(
                    code="ERR_SERIAL_GAP",
                    location=f"registry:{type_name}",
                    entity=type_name,
                    reason=f"Type {type_name} has gap(s) {missing} in serial sequence 1..{max_s}",
                    suggestion="Fill missing serials or enable allow_gaps in ledger.toml",
                ))

    return issues


def scan_codebase_references(
    root: Path,
    registry: EntityRegistry,
    config: LedgerConfig,
) -> list[LintIssue]:
    issues: list[LintIssue] = []
    registered_ids = {r.id for r in registry.rows}
    all_prefixes = [cfg.prefix for cfg in config.types.values()]
    if not all_prefixes:
        return issues

    ref_regex = re.compile(rf"\b({'|'.join(re.escape(p) for p in all_prefixes)})-([1-9][0-9]*)\b")
    code_exts = tuple(config.code_extensions)

    files_to_scan: list[Path] = []
    reg_resolved = (root / config.registry_path).resolve()

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if is_ignored(rel, config.ignore_globs):
            continue
        if p.resolve() == reg_resolved:
            continue
        if rel.endswith(code_exts) or rel.endswith(".md"):
            files_to_scan.append(p)

    for fpath in sorted(files_to_scan):
        rel = fpath.relative_to(root).as_posix()
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for lineno, line in enumerate(content.splitlines(), start=1):
            for m in ref_regex.finditer(line):
                candidate_id = f"{m.group(1)}-{m.group(2)}"
                if candidate_id not in registered_ids:
                    issues.append(LintIssue(
                        code="ERR_UNREGISTERED_ENTITY",
                        location=f"{rel}:{lineno}",
                        entity=candidate_id,
                        reason=f"References unregistered entity {candidate_id!r}",
                        suggestion=f"Allocate {candidate_id} via `repo-ledger allocate {m.group(1)} ...` or fix typo",
                    ))

    return issues


def lint_all(root: Path, registry: EntityRegistry) -> list[LintIssue]:
    issues = check_registry_invariants(registry, root)
    issues.extend(scan_codebase_references(root, registry, registry.config))
    return issues

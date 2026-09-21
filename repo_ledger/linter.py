"""Static linter for registry consistency and inverse reference scanning."""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Optional

from .config import LedgerConfig
from .registry import EntityRegistry

HASH40_RE = re.compile(r"^[0-9a-f]{40}$")


class LintIssue:
    def __init__(self, location: str, message: str, severity: str = "ERROR"):
        self.location = location
        self.message = message
        self.severity = severity

    def __str__(self) -> str:
        return f"{self.severity}: {self.location}: {self.message}"


def is_ignored(rel_path: str, ignore_globs: list[str]) -> bool:
    for pat in ignore_globs:
        if fnmatch.fnmatch(rel_path, pat) or fnmatch.fnmatch(Path(rel_path).name, pat):
            return True
        # Also check if any parent directory matches
        parts = rel_path.split("/")
        for i in range(1, len(parts)):
            sub = "/".join(parts[:i])
            if fnmatch.fnmatch(sub, pat) or fnmatch.fnmatch(sub + "/**", pat):
                return True
    return False


def check_registry_invariants(registry: EntityRegistry, root: Path) -> list[LintIssue]:
    issues: list[LintIssue] = []
    cfg = registry.config
    valid_types = set(cfg.types.keys())

    type_regex = re.compile(r"^([A-Z_]+)-([1-9][0-9]*)$")
    ids_seen: dict[str, int] = {}
    serials_per_type: dict[str, list[int]] = {}

    for row_num, row in enumerate(registry.rows, start=1):
        rid = row.id.strip()
        m = type_regex.match(rid)
        if not m:
            issues.append(LintIssue(f"registry row {row_num}", f"ID {rid!r} does not match TYPE-N format"))
            continue

        type_name, serial = m.group(1), int(m.group(2))
        ids_seen[rid] = ids_seen.get(rid, 0) + 1
        serials_per_type.setdefault(type_name, []).append(serial)

        # Status check
        t_cfg = cfg.types.get(type_name)
        if t_cfg and t_cfg.allowed_statuses:
            if row.status not in t_cfg.allowed_statuses:
                issues.append(LintIssue(
                    f"{rid}",
                    f"status {row.status!r} not in allowed statuses {t_cfg.allowed_statuses}"
                ))

        # Parent & Supersedes existence check
        all_ids = {r.id for r in registry.rows}
        if row.parent and row.parent not in all_ids:
            issues.append(LintIssue(f"{rid}", f"parent {row.parent!r} does not exist in registry"))
        if row.supersedes and row.supersedes not in all_ids:
            issues.append(LintIssue(f"{rid}", f"supersedes {row.supersedes!r} does not exist in registry"))

        # Owner check (grounding)
        if t_cfg and t_cfg.require_owner:
            owner = row.owner.strip()
            if not owner:
                issues.append(LintIssue(f"{rid}", "owner is required but empty"))
            elif not HASH40_RE.match(owner):
                owner_path = root / owner
                if not owner_path.exists():
                    issues.append(LintIssue(f"{rid}", f"owner {owner!r} does not exist on filesystem"))

    # Uniqueness check
    for rid, count in ids_seen.items():
        if count > 1:
            issues.append(LintIssue(f"ID {rid}", f"appears {count} times (must be strictly unique)"))

    # Contiguity check (1..max without gaps)
    for type_name, serials in serials_per_type.items():
        s_set = set(serials)
        max_s = max(s_set)
        expected = set(range(1, max_s + 1))
        missing = sorted(expected - s_set)
        if missing:
            issues.append(LintIssue(
                f"type {type_name}",
                f"has serial gap(s): {missing} (contiguous 1..{max_s} required)"
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

    # Collect files to scan
    files_to_scan: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if is_ignored(rel, config.ignore_globs):
            continue
        # Check if it is under registry path (skip scanning the registry file itself)
        if (root / config.registry_path).resolve() == p.resolve():
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
                        f"{rel}:{lineno}",
                        f"references unregistered entity {candidate_id!r}"
                    ))

    return issues


def lint_all(root: Path, registry: EntityRegistry) -> list[LintIssue]:
    issues = check_registry_invariants(registry, root)
    issues.extend(scan_codebase_references(root, registry, registry.config))
    return issues

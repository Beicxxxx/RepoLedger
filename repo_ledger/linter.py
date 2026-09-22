"""Read-only working tree validation with an auditable scan inventory."""
import fnmatch
from pathlib import Path
import re
from .errors import Issue, LedgerError
from .git import inventory, safe_file

def check_registry_invariants(registry, root):
    tracked, _, _ = inventory(root)
    issues = []
    rows = {r.id: r for r in registry.rows}
    def emit(code, row, reason):
        issues.append(Issue(code, f"{registry.path}:{registry.lines.get(row.id, 1)}:1",
                            row.id, reason, "Inspect the entity and its evidence; correct the cause explicitly."))
    for row in registry.rows:
        cfg = registry.config.types[row.id.rsplit("-", 1)[0]]
        anchor = row.anchor
        if not anchor and cfg.require_anchor:
            emit("ERR_MISSING_ANCHOR", row, "A tracked evidence file is required")
        elif anchor:
            if ":" in anchor or re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", anchor):
                emit("ERR_UNSUPPORTED_ANCHOR", row, "Historical anchors are not supported; no object validity is inferred")
            else:
                try:
                    path = safe_file(root, anchor)
                    if anchor not in tracked or not path.is_file():
                        emit("ERR_ANCHOR_NOT_FOUND", row, f"Anchor must be an existing tracked regular file: {anchor}")
                except LedgerError as exc:
                    emit(exc.issue.code, row, exc.issue.reason)
    for relation in ("parent", "supersedes"):
        graph = {}
        for row in registry.rows:
            targets = ([row.parent] if row.parent else []) if relation == "parent" else (
                [t.strip() for t in row.supersedes.split(",")] if row.supersedes else [])
            graph[row.id] = targets
            for target in targets:
                if target == row.id:
                    emit("ERR_SELF_REFERENCE", row, f"{relation} references itself")
                elif target not in rows:
                    emit("ERR_RELATION_NOT_FOUND", row, f"{relation} target does not exist: {target}")
        # Iterative DFS avoids recursion depth failures on long task histories.
        colors = {}
        for start in graph:
            if colors.get(start):
                continue
            stack = [(start, False)]
            while stack:
                node, leaving = stack.pop()
                if leaving:
                    colors[node] = 2
                    continue
                if colors.get(node) == 2:
                    continue
                colors[node] = 1
                stack.append((node, True))
                for target in graph[node]:
                    if target not in graph or target == node:
                        continue
                    if colors.get(target) == 1:
                        emit("ERR_RELATION_CYCLE", rows[node], f"Cycle in {relation} through {target}")
                    elif not colors.get(target):
                        stack.append((target, False))
    return issues

def scan(root, registry):
    tracked, new, git_ignored = inventory(root)
    cfg = registry.config
    audit = {"view": "worktree", "scope": "full configured text scope",
             "tracked": sorted(tracked), "untracked": sorted(new),
             "git_ignored": git_ignored, "ignore_globs": cfg.ignore_globs,
             "reference_exemptions": {path: list(tokens)
                                      for path, tokens in cfg.reference_exemptions.items()},
             "suppressed": [], "scanned": [], "excluded": []}
    issues = []
    prefixes = "|".join(re.escape(t) for t in cfg.types)
    pattern = re.compile(rf"(?<![\w-])(?:{prefixes})-[0-9]+(?![\w-])")
    known = {r.id for r in registry.rows}
    exemptions = [(path, set(tokens)) for path, tokens in cfg.reference_exemptions.items()
                  if cfg.reference_exemptions]
    for rel in sorted(tracked | new):
        reason = None
        if rel == cfg.registry_path:
            reason = "authoritative registry parsed separately"
        elif any(fnmatch.fnmatchcase(rel, p) for p in cfg.ignore_globs):
            reason = "configured ignore"
        elif Path(rel).suffix not in set(cfg.code_extensions) | {".md"}:
            reason = "extension outside scope"
        if reason:
            audit["excluded"].append({"file": rel, "reason": reason})
            continue
        try:
            content = safe_file(root, rel).read_text(encoding="utf-8")
            audit["scanned"].append(rel)
        except (OSError, UnicodeError, LedgerError) as exc:
            issues.append(Issue("ERR_SCAN_INCOMPLETE", f"{rel}:1:1", "", str(exc),
                                "Restore a readable UTF-8 regular file in the repository.", "incomplete"))
            continue
        for number, line in enumerate(content.splitlines(), 1):
            for match in pattern.finditer(line):
                if match[0] not in known:
                    exemption = next((tokens for path, tokens in exemptions
                                      if _matches_glob(rel, path) and match[0] in tokens), None)
                    if exemption is not None:
                        # Narrow, declared suppression: recorded, never silent.
                        if len(audit["suppressed"]) < 50:
                            audit["suppressed"].append(
                                {"file": rel, "line": number, "column": match.start() + 1,
                                 "token": match[0]})
                        continue
                    issues.append(Issue("ERR_UNREGISTERED_ENTITY", f"{rel}:{number}:{match.start()+1}",
                                        match[0], "Reference has no registered entity",
                                        "Lookup existing entities; fix a typo, allocate a genuinely "
                                        "new entity, or declare a narrow reference_exemptions token."))
    return issues, audit


def _matches_glob(rel, pattern):
    """Make the common ``**/name`` spelling include repository-root files."""
    return fnmatch.fnmatchcase(rel, pattern) or (
        pattern.startswith("**/") and fnmatch.fnmatchcase(rel, pattern[3:]))


def _matches_any(rel, patterns):
    return any(_matches_glob(rel, pattern) for pattern in patterns)


def _masked_by_columns(line, start, end, rel, masks):
    selected = {number for pattern, numbers in masks.items()
                if _matches_glob(rel, pattern) for number in numbers}
    if not selected:
        return False
    delimiter = "|" if "|" in line else "\t" if "\t" in line else "," if "," in line else None
    if delimiter is None:
        return False
    spans = []
    cursor = 0
    for match in re.finditer(re.escape(delimiter), line):
        spans.append((cursor, match.start()))
        cursor = match.end()
    spans.append((cursor, len(line)))
    if delimiter == "|" and line.startswith("|"):
        spans = spans[1:]
    if delimiter == "|" and line.endswith("|"):
        spans = spans[:-1]
    return any(index in selected and start >= left and end <= right
               for index, (left, right) in enumerate(spans, 1))


def _fence_start(line):
    match = re.match(r"^\s*(`{3,}|~{3,})\s*([^\s`~]*)", line)
    return (match.group(1)[0], match.group(2)) if match else None


def scan_legacy(root, registry):
    """Reject explicitly enumerated retired aliases in a declared text scope.

    The regular expression is generated only from escaped, configured literal
    tokens and registry legacy values.  Users cannot supply a shape regex.
    """
    tracked, new, git_ignored = inventory(root)
    cfg = registry.config
    guard = cfg.legacy_guard
    effective_scope = guard.scope_globs or [
        pattern
        for extension in sorted(set(cfg.code_extensions) | {".md"})
        for pattern in (f"*{extension}", f"**/*{extension}")
    ]
    audit = {
        "enabled": guard.enabled,
        "scope_globs": effective_scope,
        "exclude_globs": list(guard.exclude_globs),
        "file_exemptions": list(guard.file_exemptions),
        "column_masks": dict(guard.column_masks),
        "fence_exemptions": list(guard.fence_exemptions),
        "string_line_exemptions": dict(guard.string_line_exemptions),
        "tracked": sorted(tracked),
        "untracked": sorted(new),
        "git_ignored": git_ignored,
        "scanned": [],
        "excluded": [],
        "blind_spots": [
            "JSON object keys are not structurally audited; this is a line-oriented guard, "
            "not proof that generated or escaped key names are covered."
        ],
    }
    if not guard.enabled:
        audit["excluded"].append({"file": "<guard>", "reason": "legacy guard disabled by configuration"})
        return [], audit

    legacy_to_id = {row.legacy: row.id for row in registry.rows if row.legacy}
    tokens = sorted(set(guard.forbidden_tokens) | set(legacy_to_id), key=lambda value: (-len(value), value))
    audit["tokens"] = tokens
    if not tokens:
        return [], audit
    pattern = re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(token) for token in tokens) + r")(?![\w-])")
    issues = []
    for rel in sorted(tracked | new):
        reason = None
        if rel == cfg.registry_path:
            reason = "authoritative registry parsed separately"
        elif any(fnmatch.fnmatchcase(rel, pattern) for pattern in cfg.ignore_globs):
            reason = "configured ledger ignore"
        elif _matches_any(rel, guard.exclude_globs):
            reason = "legacy guard range exclusion"
        elif not _matches_any(rel, effective_scope):
            reason = "outside declared legacy guard scope"
        elif _matches_any(rel, guard.file_exemptions):
            reason = "legacy guard whole-file exemption"
        if reason:
            audit["excluded"].append({"file": rel, "reason": reason})
            continue
        try:
            content = safe_file(root, rel).read_text(encoding="utf-8")
            audit["scanned"].append(rel)
        except (OSError, UnicodeError, LedgerError) as exc:
            issues.append(Issue("ERR_SCAN_INCOMPLETE", f"{rel}:1:1", "", str(exc),
                                "Restore a readable UTF-8 regular file in the repository.", "incomplete"))
            continue

        fence = None
        line_patterns = [(pattern, numbers) for pattern, numbers in guard.string_line_exemptions.items()
                         if _matches_glob(rel, pattern)]
        for number, line in enumerate(content.splitlines(), 1):
            marker = _fence_start(line)
            if fence:
                if marker and marker[0] == fence[0]:
                    fence = None
                elif fence[1] in guard.fence_exemptions:
                    continue
            elif marker:
                if marker[1] in guard.fence_exemptions:
                    fence = marker
                    continue
            if any(number in numbers for _, numbers in line_patterns):
                continue
            for match in pattern.finditer(line):
                if _masked_by_columns(line, match.start(), match.end(), rel, guard.column_masks):
                    continue
                token = match[0]
                entity = legacy_to_id.get(token, token)
                issues.append(Issue(
                    "ERR_RETIRED_CODE", f"{rel}:{number}:{match.start() + 1}", entity,
                    f"Retired alias appears in the declared scan scope: {token}",
                    "Decode the alias with repo-ledger lookup and write the current ID; add only a narrow, documented exemption if this is teaching data."
                ))
    return issues, audit


def lint_all(root, registry):
    return (check_registry_invariants(registry, root) + scan(root, registry)[0]
            + scan_legacy(root, registry)[0])

def aggregate(issues):
    groups = {}
    for issue in issues:
        key = (issue.code, issue.entity, issue.reason, issue.category)
        if key not in groups:
            groups[key] = {**issue.to_dict(), "count": 0, "locations": []}
        group = groups[key]
        group["count"] += 1
        if len(group["locations"]) < 10:
            group["locations"].append(issue.location)
    return list(groups.values())

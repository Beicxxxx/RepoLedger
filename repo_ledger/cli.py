"""Public CLI; unsupported views never fall back to the worktree."""
import argparse
import json
from pathlib import Path
import sys
from .config import LedgerConfig, find_config_file
from .errors import LedgerError
from .git import repository_root, safe_file
from .linter import aggregate, check_registry_invariants, scan, scan_legacy
from .registry import EntityRegistry
from .search import search_entities

DEFAULT_CONFIG_TEMPLATE = '''[ledger]
schema_version = "1.0"
registry_path = ".ledger/ENTITY_REGISTRY.md"
allow_gaps = true
code_extensions = [".py", ".ts", ".js", ".go", ".rs", ".json", ".md"]
ignore_globs = []

[legacy_guard]
enabled = true
scope_globs = ["*.py", "**/*.py", "*.ts", "**/*.ts", "*.js", "**/*.js", "*.go", "**/*.go", "*.rs", "**/*.rs", "*.json", "**/*.json", "*.md", "**/*.md"]
exclude_globs = []
forbidden_tokens = []
file_exemptions = []
column_masks = {}
fence_exemptions = []
string_line_exemptions = {}
'''

def output(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))

def main(argv=None):
    parser = argparse.ArgumentParser(prog="repo-ledger")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "allocate", "lookup", "search", "update", "check", "check-legacy", "tree"):
        p = commands.add_parser(command)
        p.add_argument("--root", type=Path)
        p.add_argument("--json", action="store_true")
        if command == "allocate":
            p.add_argument("type")
            p.add_argument("name")
            for flag in ("anchor", "status", "parent", "supersedes", "note", "legacy"):
                p.add_argument("--" + flag, default=None if flag == "status" else "")
        if command == "lookup":
            p.add_argument("entity_id")
        if command == "search":
            p.add_argument("query")
            p.add_argument("--limit", type=int, default=5)
        if command == "update":
            p.add_argument("entity_id")
            p.add_argument("--status")
            p.add_argument("--note")
            p.add_argument("--expected-status")
        if command == "check":
            p.add_argument("--staged", action="store_true")
            p.add_argument("--commit")
            p.add_argument("--incremental", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "check" and (args.staged or args.commit or args.incremental):
            raise LedgerError("ERR_UNSUPPORTED_VIEW", "Index, commit-tree and incremental checks are not implemented",
                              category="configuration")
        cfg_path = find_config_file(args.root)
        if args.command == "init":
            root = (args.root or Path.cwd()).resolve()
            repository_root(root)
            cfg_path = root / "ledger.toml"
            if cfg_path.exists() or (root / ".ledger/ENTITY_REGISTRY.md").exists():
                raise LedgerError("ERR_ALREADY_INITIALIZED", "Refusing to overwrite existing configuration or registry")
            # Exclusive creation protects existing user configuration.
            with cfg_path.open("x", encoding="utf-8") as stream:
                stream.write(DEFAULT_CONFIG_TEMPLATE)
            cfg = LedgerConfig.load(cfg_path)
            path = safe_file(root, cfg.registry_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as stream:
                stream.write("<!-- schema: 1.0 -->\n# Entity Registry\n\n"
                             "| id | name | status | parent | order | anchor | supersedes | date | legacy | note |\n"
                             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
            output({"status": "INITIALIZED", "root": str(root)})
            return 0
        if cfg_path is None:
            raise LedgerError("ERR_CONFIG", "No ledger.toml; run init at the repository root", category="configuration")
        root = repository_root(cfg_path.parent)
        cfg = LedgerConfig.load(cfg_path)
        registry = EntityRegistry.load(safe_file(root, cfg.registry_path), cfg)
        if args.command == "allocate":
            row = registry.allocate(args.type, args.name, args.status, args.parent, args.anchor,
                                    args.supersedes, args.note, args.legacy)
            output(row.to_dict())
        elif args.command == "search":
            result = search_entities(registry, args.query, args.limit)
            if args.json:
                output(result)
            else:
                print(f"{result['total']} matches; showing {len(result['results'])}")
                for row in result["results"]:
                    print(f"{row['id']} [{row['status']}] {row['name']} anchor={row['anchor'] or '-'}")
        elif args.command == "update":
            row = registry.update(args.entity_id, status=args.status, note=args.note,
                                  expected_status=args.expected_status)
            if args.json:
                output(row.to_dict())
            else:
                print(f"Updated {row.id} [{row.status}] {row.name}")
        elif args.command == "lookup":
            row = registry.lookup(args.entity_id)
            if row is None:
                raise LedgerError("ERR_UNREGISTERED_ENTITY", "Entity not found", entity=args.entity_id)
            if args.json:
                output(row.to_dict())
            else:
                print(f"ID:         {row.id}\nName:       {row.name}\nStatus:     {row.status}\n"
                      f"Anchor:     {row.anchor}\nLegacy:     {row.legacy}")
        elif args.command == "tree":
            # Retained prototype convenience; validation prevents cycles.
            issues = check_registry_invariants(registry, root)
            if issues:
                issue = issues[0]
                raise LedgerError(issue.code, issue.reason, issue.location, issue.entity)
            for row in registry.rows:
                print(f"{row.id} [{row.status}] {row.name} parent={row.parent or '-'}")
        elif args.command == "check-legacy":
            legacy_issues, legacy_audit = scan_legacy(root, registry)
            scope = {"view": "worktree", "legacy_guard": legacy_audit}
            result = {"status": "FAIL" if legacy_issues else "PASS", "entities_count": len(registry.rows),
                      "complete": not any(i.category == "incomplete" for i in legacy_issues),
                      "scope": scope, "issues": aggregate(legacy_issues)}
            if args.json:
                output(result)
            else:
                print(f"{result['status']}: legacy guard, {len(legacy_audit['scanned'])} files scanned")
                for issue in result["issues"]:
                    print(f"[{issue['code']}] {issue['location']} {issue['entity']}: {issue['reason']} "
                          f"(count={issue['count']}); {issue['suggestion']}")
            return 3 if not result["complete"] else int(bool(legacy_issues))
        else:
            issues = check_registry_invariants(registry, root)
            scanned, audit = scan(root, registry)
            issues += scanned
            legacy_issues, legacy_audit = scan_legacy(root, registry)
            issues += legacy_issues
            audit["legacy_guard"] = legacy_audit
            result = {"status": "FAIL" if issues else "PASS", "entities_count": len(registry.rows),
                      "complete": not any(i.category == "incomplete" for i in issues),
                      "scope": audit, "issues": aggregate(issues)}
            if args.json:
                output(result)
            else:
                print(f"{result['status']}: worktree, {len(audit['scanned'])} files scanned")
                for issue in result["issues"]:
                    print(f"[{issue['code']}] {issue['location']} {issue['entity']}: {issue['reason']} "
                          f"(count={issue['count']}); {issue['suggestion']}")
            return 3 if not result["complete"] else int(bool(issues))
        return 0
    except (LedgerError, OSError, UnicodeError) as exc:
        if not isinstance(exc, LedgerError):
            exc = LedgerError("ERR_READ_WRITE", str(exc), category="incomplete")
        issue = exc.issue
        if issue.code == "ERR_UPDATE_CONFLICT":
            issue.suggestion = "Run lookup again, review the current evidence, and retry only if the update is still valid."
        elif issue.code == "ERR_NO_UPDATE":
            issue.suggestion = "Specify --status and/or --note; use an empty --note to clear the note."
        elif issue.code == "ERR_SEARCH_QUERY":
            issue.suggestion = "Supply a nonblank literal keyword, ID, or documented legacy alias."
        elif issue.code == "ERR_SEARCH_LIMIT":
            issue.suggestion = "Choose --limit from 1 through 100; the default is 5."
        elif issue.code == "ERR_LEGACY_READONLY":
            issue.suggestion = "Resolve the alias with lookup, then update the returned current ID; never reassign the alias."
        elif issue.code == "ERR_REGISTRY_PATH_CHANGED":
            issue.suggestion = "Reload ledger.toml and lookup the entity in the configured registry before retrying."
        if args.json:
            output({"status": "FAIL", "complete": False, "issues": [issue.to_dict()]})
        else:
            print(f"[{issue.code}] {issue.location} {issue.entity}: {issue.reason}; {issue.suggestion}", file=sys.stderr)
        return {"violation": 1, "configuration": 2, "incomplete": 3}[issue.category]

if __name__ == "__main__":
    sys.exit(main())

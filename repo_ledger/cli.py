"""Command-line interface for repo-ledger."""
from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path
from typing import Optional

from .config import LedgerConfig, find_config_file
from .linter import lint_all
from .registry import EntityRegistry


DEFAULT_CONFIG_TEMPLATE = """# RepoLedger Configuration
[ledger]
version = "1.0"
registry_path = ".ledger/ENTITY_REGISTRY.md"
doc_dirs = ["docs", ".ai/state", ".ai/handoff"]
code_extensions = [".py", ".ts", ".js", ".go", ".rs", ".json"]
ignore_globs = [
    "node_modules/**", "dist/**", "build/**", ".git/**", "tests/fixtures/**", "*.egg-info/**"
]

[types.TASK]
prefix = "TASK"
allowed_statuses = ["BACKLOG", "IN_PROGRESS", "BLOCKED", "DONE", "DROPPED"]
require_owner = true
description = "Actionable engineering or research tasks"

[types.DECISION]
prefix = "DECISION"
allowed_statuses = ["DRAFT", "IN_FORCE", "SUPERSEDED"]
require_owner = true
description = "Architecture Decision Records and policy rulings"

[types.EXP]
prefix = "EXP"
allowed_statuses = ["PLANNED", "RUNNING", "VALIDATING", "DONE", "FAILED", "INVALID"]
require_owner = true
description = "Reproducible experiments and benchmarks"

[types.ISSUE]
prefix = "ISSUE"
allowed_statuses = ["OPEN", "INVESTIGATING", "RESOLVED", "WONT_FIX"]
require_owner = true
description = "Defects, regressions, and blockers"

[types.GATE]
prefix = "GATE"
allowed_statuses = ["DRAFT", "IN_FORCE", "SUPERSEDED", "DONE"]
require_owner = true
description = "Verification milestones and quality gates"
"""


def cmd_init(args: argparse.Namespace) -> int:
    root = Path.cwd()
    config_file = root / "ledger.toml"
    if config_file.exists() and not args.force:
        print(f"[repo-ledger] Config already exists at {config_file}. Use --force to overwrite.")
    else:
        config_file.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
        print(f"[repo-ledger] Created configuration at {config_file}")

    config = LedgerConfig.load(config_file)
    registry_file = root / config.registry_path
    if not registry_file.exists() or args.force:
        registry = EntityRegistry(registry_file, config)
        registry.save()
        print(f"[repo-ledger] Initialized empty registry at {registry_file}")
    else:
        print(f"[repo-ledger] Registry already exists at {registry_file}")

    return 0


def cmd_allocate(args: argparse.Namespace) -> int:
    cfg_path = find_config_file()
    root = cfg_path.parent if cfg_path else Path.cwd()
    config = LedgerConfig.load(cfg_path) if cfg_path else LedgerConfig.default()

    reg_path = root / config.registry_path
    registry = EntityRegistry.load(reg_path, config)

    type_name = args.type.upper()
    row = registry.allocate(
        type_name=type_name,
        name=args.name,
        status=args.status,
        parent=args.parent or "",
        owner=args.owner or "",
        supersedes=args.supersedes or "",
        note=args.note or "",
    )
    registry.save()

    print(f"[repo-ledger] Allocated: {row.id} - {row.name} ({row.status})")
    print(f"             Registry updated: {reg_path}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    cfg_path = find_config_file(args.root)
    root = (args.root or (cfg_path.parent if cfg_path else Path.cwd())).resolve()
    config = LedgerConfig.load(cfg_path) if cfg_path else LedgerConfig.default()

    reg_path = root / config.registry_path
    if not reg_path.is_file():
        print(f"[repo-ledger] FAIL: Registry file not found at {reg_path}", file=sys.stderr)
        return 1

    registry = EntityRegistry.load(reg_path, config)
    issues = lint_all(root, registry)

    if not issues:
        print(f"[repo-ledger] PASS: All {len(registry.rows)} registered entities valid, zero dangling references.")
        return 0

    print(f"\n[repo-ledger] FAILED with {len(issues)} issue(s):")
    for issue in issues:
        print(f"  {issue}")
    return 1


def cmd_tree(args: argparse.Namespace) -> int:
    cfg_path = find_config_file()
    root = cfg_path.parent if cfg_path else Path.cwd()
    config = LedgerConfig.load(cfg_path) if cfg_path else LedgerConfig.default()

    reg_path = root / config.registry_path
    if not reg_path.is_file():
        print(f"[repo-ledger] Registry file not found at {reg_path}", file=sys.stderr)
        return 1

    registry = EntityRegistry.load(reg_path, config)
    children: dict[str, list] = {}
    roots = []

    for r in registry.rows:
        if r.parent:
            children.setdefault(r.parent, []).append(r)
        else:
            roots.append(r)

    def print_node(node, prefix="", is_last=True):
        connector = "`-- " if is_last else "|-- "
        print(f"{prefix}{connector}{node.id} [{node.status}] {node.name}")
        child_prefix = prefix + ("    " if is_last else "|   ")
        ch_list = children.get(node.id, [])
        for i, ch in enumerate(ch_list):
            print_node(ch, child_prefix, i == len(ch_list) - 1)

    print(f"\nEntity Hierarchy ({len(registry.rows)} entities):")
    for i, root_node in enumerate(roots):
        print_node(root_node, "", i == len(roots) - 1)
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    if args.hook_action == "install":
        root = Path.cwd()
        git_dir = root / ".git"
        if not git_dir.is_dir():
            print("[repo-ledger] Error: .git directory not found. Must run from repository root.", file=sys.stderr)
            return 1

        hook_file = git_dir / "hooks" / "pre-commit"
        hook_file.parent.mkdir(parents=True, exist_ok=True)

        hook_script = "#!/bin/sh\nrepo-ledger check\n"
        hook_file.write_text(hook_script, encoding="utf-8")

        # Make executable
        st = hook_file.stat()
        hook_file.chmod(st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        print(f"[repo-ledger] Installed pre-commit hook to {hook_file}")
        return 0
    return 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="repo-ledger",
        description="Git-native Entity & Knowledge Governance for AI Coding Agent Swarms",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize repo-ledger configuration and registry")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing configuration")
    p_init.set_defaults(func=cmd_init)

    # allocate
    p_alloc = subparsers.add_parser("allocate", help="Allocate the next sequential entity ID")
    p_alloc.add_argument("type", help="Entity type (e.g. TASK, DECISION, EXP, ISSUE, GATE)")
    p_alloc.add_argument("name", help="Short name or title of the entity")
    p_alloc.add_argument("--status", help="Initial status")
    p_alloc.add_argument("--parent", help="Parent entity ID")
    p_alloc.add_argument("--owner", help="Authoritative artifact file path or commit hash")
    p_alloc.add_argument("--supersedes", help="Previous entity ID this supersedes")
    p_alloc.add_argument("--note", help="Optional historical note or context")
    p_alloc.set_defaults(func=cmd_allocate)

    # check
    p_check = subparsers.add_parser("check", help="Statically verify entity invariants and references")
    p_check.add_argument("--root", type=Path, help="Root repository directory to scan")
    p_check.set_defaults(func=cmd_check)

    # tree
    p_tree = subparsers.add_parser("tree", help="Display hierarchical dependency tree of entities")
    p_tree.set_defaults(func=cmd_tree)

    # hook
    p_hook = subparsers.add_parser("hook", help="Manage git hooks")
    p_hook.add_argument("hook_action", choices=["install"], help="Action to perform")
    p_hook.set_defaults(func=cmd_hook)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

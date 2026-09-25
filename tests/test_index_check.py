"""``repo-ledger check`` integration of the index staleness check (written red-first)."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from repo_ledger.cli import main
from repo_ledger.config import LedgerConfig
from repo_ledger.linter import lint_all
from repo_ledger.registry import EntityRegistry

TYPES = """
[types.TASK]
allowed_statuses = ["BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE", "DROPPED"]

[types.ISSUE]
allowed_statuses = ["OPEN", "INVESTIGATING", "RESOLVED", "WONT_FIX"]
"""
REGISTRY_HEAD = (
    "<!-- schema: 1.0 -->\n# Entity Registry\n\n"
    "| id | name | status | parent | order | anchor | supersedes | date | legacy | note |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
ROWS = (
    "| TASK-1 | Alpha | READY |  | 1 | docs/proposal.md |  | 2026-09-01 | OLD-TASK-1 |  |\n"
    "| ISSUE-1 | Bug | OPEN | TASK-1 | 1 | docs/proposal.md |  | 2026-09-02 |  | found in TASK-1 |\n")
PAGES = ["docs/index/README.md", "docs/index/TASK.md", "docs/index/ISSUE.md"]
VERIFIED = "generated index page verified by the index check"


def make_repo(root: Path, index_table: str, rows: str = ROWS) -> Path:
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    config = '[ledger]\nschema_version = "1.0"\nregistry_path = ".ledger/ENTITY_REGISTRY.md"\n' + TYPES
    if index_table:
        config += "\n[index]\n" + index_table
    (root / "ledger.toml").write_text(config, encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
    (root / ".ledger").mkdir()
    (root / ".ledger" / "ENTITY_REGISTRY.md").write_text(REGISTRY_HEAD + rows, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    return root


def run(capsys, root: Path, *args: str):
    capsys.readouterr()
    code = main([*args, "--root", str(root), "--json"])
    return code, json.loads(capsys.readouterr().out)


def generate(capsys, root: Path, *extra: str) -> None:
    code, report = run(capsys, root, "index", *extra)
    assert code == 0, report


def reasons(entries):
    return {entry["file"]: entry["reason"] for entry in entries}


def test_fresh_index_passes_check_and_generated_pages_are_not_rescanned(tmp_path, capsys):
    root = make_repo(tmp_path, 'out_dir = "docs/index"\ncheck = true\n')
    generate(capsys, root)

    code, report = run(capsys, root, "check")
    assert code == 0, report["issues"]
    assert set(report) == {"status", "entities_count", "complete", "scope", "issues"}
    assert report["status"] == "PASS" and report["complete"] is True
    index = report["scope"]["index"]
    assert index["out_dir"] == "docs/index"
    assert index["pages"] == PAGES
    assert (index["missing"], index["stale"], index["extra"]) == ([], [], [])
    assert index["registry_sha256"] == hashlib.sha256(
        (root / ".ledger" / "ENTITY_REGISTRY.md").read_bytes()).hexdigest()
    # The legacy alias rendered on TASK.md is registry content, verified by regeneration.
    for page in PAGES:
        assert reasons(report["scope"]["excluded"])[page] == VERIFIED
        assert reasons(report["scope"]["legacy_guard"]["excluded"])[page] == VERIFIED
        assert page not in report["scope"]["scanned"]


def test_stale_index_fails_check_with_located_issues(tmp_path, capsys):
    root = make_repo(tmp_path, 'out_dir = "docs/index"\ncheck = true\n')
    generate(capsys, root)
    code, _ = run(capsys, root, "update", "TASK-1", "--status", "DONE")
    assert code == 0

    code, report = run(capsys, root, "check")
    assert code == 1 and report["status"] == "FAIL"
    stale = [issue for issue in report["issues"] if issue["code"] == "ERR_INDEX_STALE"]
    assert [location for issue in stale for location in issue["locations"]] == [
        f"{page}:1:1" for page in PAGES]
    assert all("differs" in issue["reason"] and "repo-ledger index" in issue["suggestion"]
               for issue in stale)
    assert report["scope"]["index"]["stale"] == PAGES
    assert [issue["code"] for issue in report["issues"]] == ["ERR_INDEX_STALE"]

    generate(capsys, root)
    assert run(capsys, root, "check")[0] == 0


def test_missing_and_extra_pages_fail_check(tmp_path, capsys):
    root = make_repo(tmp_path, 'out_dir = "docs/index"\ncheck = true\n')
    generate(capsys, root)
    (root / "docs" / "index" / "ISSUE.md").unlink()
    (root / "docs" / "index" / "notes.md").write_text("TASK-1 Alpha\n", encoding="utf-8")

    code, report = run(capsys, root, "check")
    assert code == 1
    index = report["scope"]["index"]
    assert (index["missing"], index["stale"], index["extra"]) == (
        ["docs/index/ISSUE.md"], [], ["docs/index/notes.md"])
    located = {issue["locations"][0]: issue for issue in report["issues"]}
    assert located["docs/index/ISSUE.md:1:1"]["code"] == "ERR_INDEX_STALE"
    assert "missing" in located["docs/index/ISSUE.md:1:1"]["reason"]
    assert located["docs/index/notes.md:1:1"]["code"] == "ERR_INDEX_STALE"
    assert "not generated" in located["docs/index/notes.md:1:1"]["reason"]
    # An unknown page is not generated content, so it is still scanned like any file.
    assert "docs/index/notes.md" in report["scope"]["scanned"]


def test_index_table_without_check_leaves_check_unchanged(tmp_path, capsys):
    rows = ROWS.replace("OLD-TASK-1", "")
    root = make_repo(tmp_path, 'out_dir = "docs/index"\n', rows)
    generate(capsys, root)
    registry = root / ".ledger" / "ENTITY_REGISTRY.md"
    registry.write_text(registry.read_text(encoding="utf-8").replace("| Alpha |", "| Alpha two |"),
                        encoding="utf-8")

    code, report = run(capsys, root, "check")
    assert code == 0, report["issues"]
    assert "index" not in report["scope"]
    assert all(page in report["scope"]["scanned"] for page in PAGES)
    assert VERIFIED not in reasons(report["scope"]["excluded"]).values()


def test_pages_are_ordinary_files_when_check_is_off(tmp_path, capsys):
    root = make_repo(tmp_path, 'out_dir = "docs/index"\n')
    generate(capsys, root)

    # Without check = true the pages are not verified, so they are scanned like any Markdown:
    # the registry's legacy alias rendered on TASK.md trips the retired-code guard.
    code, report = run(capsys, root, "check")
    assert code == 1
    assert [(issue["code"], issue["locations"][0].split(":")[0]) for issue in report["issues"]] == [
        ("ERR_RETIRED_CODE", "docs/index/TASK.md")]


def test_projects_without_index_table_see_no_change(tmp_path, capsys):
    rows = ROWS.replace("OLD-TASK-1", "")
    root = make_repo(tmp_path, "", rows)
    generate(capsys, root, "--out", str(root / "docs" / "index"))
    registry = root / ".ledger" / "ENTITY_REGISTRY.md"
    registry.write_text(registry.read_text(encoding="utf-8").replace("| Alpha |", "| Alpha two |"),
                        encoding="utf-8")

    code, report = run(capsys, root, "check")
    assert code == 0, report["issues"]
    assert set(report) == {"status", "entities_count", "complete", "scope", "issues"}
    assert set(report["scope"]) == {"view", "scope", "tracked", "untracked", "git_ignored", "ignore_globs",
                                    "reference_exemptions", "suppressed", "scanned", "excluded",
                                    "legacy_guard"}
    assert all(page in report["scope"]["scanned"] for page in PAGES)


def test_check_legacy_skips_verified_generated_pages(tmp_path, capsys):
    root = make_repo(tmp_path, 'out_dir = "docs/index"\ncheck = true\n')
    generate(capsys, root)

    code, report = run(capsys, root, "check-legacy")
    assert code == 0, report["issues"]
    for page in PAGES:
        assert reasons(report["scope"]["legacy_guard"]["excluded"])[page] == VERIFIED


def test_unverifiable_index_makes_check_incomplete(tmp_path, capsys):
    rows = ROWS.replace("| OPEN | TASK-1 |", "| OPEN | TASK-9 |")
    root = make_repo(tmp_path, 'out_dir = "docs/index"\ncheck = true\n', rows)

    code, report = run(capsys, root, "check")
    assert code == 3
    assert report["complete"] is False
    codes = [issue["code"] for issue in report["issues"]]
    assert "ERR_RELATION_NOT_FOUND" in codes and "ERR_INDEX_UNVERIFIED" in codes


def test_lint_all_mirrors_the_check_integration(tmp_path, capsys):
    root = make_repo(tmp_path, 'out_dir = "docs/index"\ncheck = true\n')
    generate(capsys, root)
    config = LedgerConfig.load(root / "ledger.toml")
    registry = EntityRegistry.load(root / config.registry_path, config)
    assert lint_all(root, registry) == []

    (root / "docs" / "index" / "TASK.md").unlink()
    assert [issue.code for issue in lint_all(root, registry)] == ["ERR_INDEX_STALE"]

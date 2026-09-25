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
CHECKED = 'out_dir = "docs/index"\ncheck = true\n'


def make_repo(root: Path, index_table: str, rows: str = ROWS, guard: str = "") -> Path:
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    config = '[ledger]\nschema_version = "1.0"\nregistry_path = ".ledger/ENTITY_REGISTRY.md"\n' + TYPES
    if guard:
        config += "\n[legacy_guard]\n" + guard
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


def located(report):
    """(code, location) of every reported occurrence."""
    return sorted((issue["code"], location) for issue in report["issues"] for location in issue["locations"])


def position(root: Path, page: str, token: str, occurrence: int = 0) -> str:
    """page:line:column of a token, as the scanners report it."""
    hits = [f"{page}:{number}:{line.index(token) + 1}"
            for number, line in enumerate((root / page).read_text(encoding="utf-8").splitlines(), 1)
            if token in line]
    return hits[occurrence]


def load_registry(root: Path) -> EntityRegistry:
    config = LedgerConfig.load(root / "ledger.toml")
    return EntityRegistry.load(root / config.registry_path, config)


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
    assert all("hits on it disappear once it is regenerated" in issue["suggestion"] for issue in stale)
    assert report["scope"]["index"]["stale"] == PAGES
    # A stale page is not verified, so it is scanned like any file until it is regenerated:
    # the legacy alias rendered on TASK.md is reported with it.
    assert [issue["code"] for issue in report["issues"]] == ["ERR_RETIRED_CODE", "ERR_INDEX_STALE"]
    assert report["issues"][0]["locations"] == [position(root, "docs/index/TASK.md", "OLD-TASK-1")]
    assert VERIFIED not in reasons(report["scope"]["excluded"]).values()

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
    root = make_repo(tmp_path, 'out_dir = "docs/index"\ncheck = true\n')
    generate(capsys, root)
    registry = root / ".ledger" / "ENTITY_REGISTRY.md"
    registry.write_text(registry.read_text(encoding="utf-8").replace("| OPEN | TASK-1 |", "| OPEN | TASK-9 |"),
                        encoding="utf-8")

    code, report = run(capsys, root, "check")
    assert code == 3
    assert report["complete"] is False
    codes = [issue["code"] for issue in report["issues"]]
    assert "ERR_RELATION_NOT_FOUND" in codes and "ERR_INDEX_UNVERIFIED" in codes
    # Pages that could not be verified are ordinary files again: no "verified" exclusion.
    assert VERIFIED not in reasons(report["scope"]["excluded"]).values()
    assert all(page in report["scope"]["scanned"] for page in PAGES)
    assert report["scope"]["index"]["registry_sha256"] is None


def test_lint_all_mirrors_the_check_integration(tmp_path, capsys):
    root = make_repo(tmp_path, 'out_dir = "docs/index"\ncheck = true\n')
    generate(capsys, root)
    config = LedgerConfig.load(root / "ledger.toml")
    registry = EntityRegistry.load(root / config.registry_path, config)
    assert lint_all(root, registry) == []

    (root / "docs" / "index" / "TASK.md").unlink()
    assert [issue.code for issue in lint_all(root, registry)] == ["ERR_INDEX_STALE"]


# Only pages that match their regeneration byte for byte are excluded from the scans; a
# tampered, hand-written or symlinked page is scanned like any other file.
TAMPERED = "Tampered: see TASK-99 and OLD-TASK-1 and oldcode7.\n"


def test_tampered_page_is_scanned_until_it_is_regenerated(tmp_path, capsys):
    root = make_repo(tmp_path, CHECKED, guard='forbidden_tokens = ["oldcode7"]\n')
    generate(capsys, root)
    page = root / "docs" / "index" / "TASK.md"
    page.write_text(page.read_text(encoding="utf-8") + TAMPERED, encoding="utf-8")

    code, report = run(capsys, root, "check")
    assert code == 1
    task = "docs/index/TASK.md"
    assert located(report) == sorted([
        ("ERR_UNREGISTERED_ENTITY", position(root, task, "TASK-99")),
        ("ERR_RETIRED_CODE", position(root, task, "OLD-TASK-1", 0)),
        ("ERR_RETIRED_CODE", position(root, task, "OLD-TASK-1", 1)),
        ("ERR_RETIRED_CODE", position(root, task, "oldcode7")),
        ("ERR_INDEX_STALE", f"{task}:1:1")])
    assert report["scope"]["index"]["stale"] == [task]
    assert task in report["scope"]["scanned"] and task in report["scope"]["legacy_guard"]["scanned"]
    assert task not in reasons(report["scope"]["excluded"])
    assert task not in reasons(report["scope"]["legacy_guard"]["excluded"])
    # The untouched pages still verify, so they stay excluded.
    for untouched in ("docs/index/README.md", "docs/index/ISSUE.md"):
        assert reasons(report["scope"]["excluded"])[untouched] == VERIFIED
        assert reasons(report["scope"]["legacy_guard"]["excluded"])[untouched] == VERIFIED

    # lint_all applies the same rule.
    assert sorted((issue.code, issue.location) for issue in lint_all(root, load_registry(root))) == located(report)

    # Regenerating replaces the tampered page and every hit on it disappears.
    generate(capsys, root)
    code, report = run(capsys, root, "check")
    assert code == 0, report["issues"]
    assert lint_all(root, load_registry(root)) == []


def test_hand_written_page_at_a_page_path_is_scanned(tmp_path, capsys):
    root = make_repo(tmp_path, CHECKED)
    generate(capsys, root)
    issue_page = "docs/index/ISSUE.md"
    (root / issue_page).write_text("Hand-written: TASK-77 and OLD-TASK-1\n", encoding="utf-8")

    code, report = run(capsys, root, "check")
    assert code == 1
    assert located(report) == sorted([
        ("ERR_UNREGISTERED_ENTITY", position(root, issue_page, "TASK-77")),
        ("ERR_RETIRED_CODE", position(root, issue_page, "OLD-TASK-1")),
        ("ERR_INDEX_STALE", f"{issue_page}:1:1")])
    assert issue_page in report["scope"]["scanned"]
    assert issue_page not in reasons(report["scope"]["excluded"])
    assert sorted((issue.code, issue.location) for issue in lint_all(root, load_registry(root))) == located(report)


def test_symlinked_page_is_not_trusted(tmp_path, capsys):
    root = make_repo(tmp_path, CHECKED)
    generate(capsys, root)
    page = root / "docs" / "index" / "TASK.md"
    page.unlink()
    page.symlink_to(Path("..") / ".." / "ledger.toml")

    code, report = run(capsys, root, "check")
    # The link is reported missing and is not excluded; scanning refuses to follow it.
    assert code == 3 and report["complete"] is False
    task = "docs/index/TASK.md"
    assert report["scope"]["index"]["missing"] == [task]
    assert task not in reasons(report["scope"]["excluded"])
    assert task not in reasons(report["scope"]["legacy_guard"]["excluded"])
    assert located(report) == sorted([("ERR_INDEX_STALE", f"{task}:1:1"),
                                      ("ERR_SCAN_INCOMPLETE", f"{task}:1:1"),
                                      ("ERR_SCAN_INCOMPLETE", f"{task}:1:1")])
    assert sorted(issue.code for issue in lint_all(root, load_registry(root))) == [
        "ERR_INDEX_STALE", "ERR_SCAN_INCOMPLETE", "ERR_SCAN_INCOMPLETE"]


# check-legacy runs the same comparison as check and excludes only the verified pages.
def test_check_legacy_scans_a_tampered_page(tmp_path, capsys):
    root = make_repo(tmp_path, CHECKED, guard='forbidden_tokens = ["oldcode7"]\n')
    generate(capsys, root)
    page = root / "docs" / "index" / "TASK.md"
    page.write_text(page.read_text(encoding="utf-8") + TAMPERED, encoding="utf-8")

    code, report = run(capsys, root, "check-legacy")
    assert code == 1 and report["status"] == "FAIL"
    task = "docs/index/TASK.md"
    assert located(report) == sorted([("ERR_RETIRED_CODE", position(root, task, "OLD-TASK-1", 0)),
                                      ("ERR_RETIRED_CODE", position(root, task, "OLD-TASK-1", 1)),
                                      ("ERR_RETIRED_CODE", position(root, task, "oldcode7"))])
    guard = report["scope"]["legacy_guard"]
    assert task in guard["scanned"] and task not in reasons(guard["excluded"])
    for untouched in ("docs/index/README.md", "docs/index/ISSUE.md"):
        assert reasons(guard["excluded"])[untouched] == VERIFIED


def test_check_legacy_scans_a_hand_written_page(tmp_path, capsys):
    root = make_repo(tmp_path, CHECKED)
    generate(capsys, root)
    (root / "docs" / "index" / "ISSUE.md").write_text("Hand-written: OLD-TASK-1\n", encoding="utf-8")

    code, report = run(capsys, root, "check-legacy")
    assert code == 1 and report["status"] == "FAIL"
    assert located(report) == [("ERR_RETIRED_CODE", position(root, "docs/index/ISSUE.md", "OLD-TASK-1"))]


def test_check_legacy_scans_pages_that_cannot_be_regenerated(tmp_path, capsys):
    root = make_repo(tmp_path, CHECKED)
    generate(capsys, root)
    registry = root / ".ledger" / "ENTITY_REGISTRY.md"
    registry.write_text(registry.read_text(encoding="utf-8").replace("| OPEN | TASK-1 |", "| OPEN | TASK-9 |"),
                        encoding="utf-8")

    code, report = run(capsys, root, "check-legacy")
    assert code == 1 and report["status"] == "FAIL"
    assert located(report) == [("ERR_RETIRED_CODE", position(root, "docs/index/TASK.md", "OLD-TASK-1"))]
    guard = report["scope"]["legacy_guard"]
    assert all(page in guard["scanned"] for page in PAGES)
    assert VERIFIED not in reasons(guard["excluded"]).values()


def test_check_legacy_scans_pages_when_the_index_check_is_off(tmp_path, capsys):
    root = make_repo(tmp_path, 'out_dir = "docs/index"\n')
    generate(capsys, root)

    code, report = run(capsys, root, "check-legacy")
    assert code == 1
    assert located(report) == [("ERR_RETIRED_CODE", position(root, "docs/index/TASK.md", "OLD-TASK-1"))]
    assert VERIFIED not in reasons(report["scope"]["legacy_guard"]["excluded"]).values()


def test_symlinked_out_dir_is_a_configuration_error_for_check(tmp_path, capsys):
    root = make_repo(tmp_path, CHECKED)
    (root / "catalogue").mkdir()
    (root / "docs" / "index").symlink_to(root / "catalogue")

    for command in ("check", "check-legacy"):
        code, report = run(capsys, root, command)
        assert code == 2, command
        issue = report["issues"][0]
        assert issue["code"] == "ERR_INDEX_OUT_DIR" and issue["category"] == "configuration"
        assert "docs/index" in issue["reason"] and "out_dir" in issue["suggestion"]

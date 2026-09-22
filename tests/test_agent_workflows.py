"""Deterministic CLI regressions for agent-facing RepoLedger workflows."""

from __future__ import annotations

import io
import json
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from repo_ledger.cli import main


ROW_FIELDS = {
    "id",
    "name",
    "status",
    "parent",
    "order",
    "anchor",
    "supersedes",
    "date",
    "legacy",
    "note",
}
SEARCH_FIELDS = {
    "id",
    "name",
    "status",
    "anchor",
    "parent",
    "supersedes",
    "legacy",
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def isolated_git_repo(tmp_path: Path) -> Path:
    """Create a real Git repository with a tracked anchor for CLI allocations."""
    _git(tmp_path, "init")
    with redirect_stdout(io.StringIO()):
        assert main(["init", "--root", str(tmp_path)]) == 0

    (tmp_path / "evidence.md").write_text("# Evidence\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    return tmp_path


def _json_command(capsys, repo: Path, args: list[str], expected_rc: int = 0) -> dict:
    rc = main([*args, "--root", str(repo), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == expected_rc
    return payload


def _allocate(
    capsys,
    repo: Path,
    name: str,
    *,
    status: str = "READY",
    legacy: str = "",
    note: str = "",
) -> dict:
    args = [
        "allocate",
        "TASK",
        name,
        "--anchor",
        "evidence.md",
        "--status",
        status,
    ]
    if legacy:
        args.extend(["--legacy", legacy])
    if note:
        args.extend(["--note", note])
    return _json_command(capsys, repo, args)


def _ledger_state(repo: Path) -> dict[str, bytes | None]:
    paths = {
        "registry": repo / ".ledger" / "ENTITY_REGISTRY.md",
        "config": repo / "ledger.toml",
        "serials": repo / ".git" / "repo-ledger-serials.json",
    }
    return {
        name: path.read_bytes() if path.exists() else None
        for name, path in paths.items()
    }


def test_search_json_is_bounded_and_read_only(isolated_git_repo: Path, capsys) -> None:
    repo = isolated_git_repo
    for number in range(1, 8):
        _allocate(capsys, repo, f"Needle match {number}", note=f"private note {number}")
    _allocate(capsys, repo, "Unrelated task", status="DONE", note="outside query")

    before = _ledger_state(repo)
    report = _json_command(capsys, repo, ["search", "needle", "--limit", "5"])

    assert set(report) == {"query", "total", "limit", "results"}
    assert report["query"] == "needle"
    assert report["total"] == 7
    assert report["limit"] == 5
    assert len(report["results"]) == 5
    assert [row["id"] for row in report["results"]] == [
        "TASK-1",
        "TASK-2",
        "TASK-3",
        "TASK-4",
        "TASK-5",
    ]
    assert all(set(row) == SEARCH_FIELDS for row in report["results"])
    assert all(row["name"].startswith("Needle match ") for row in report["results"])
    assert _ledger_state(repo) == before


def test_lookup_resolves_exact_legacy_and_rejects_unknown_shorthand(
    isolated_git_repo: Path, capsys
) -> None:
    repo = isolated_git_repo
    _allocate(capsys, repo, "Legacy target", legacy="task36")
    for number in range(2, 37):
        name = "Task 36" if number == 36 else f"Unrelated task {number}"
        _allocate(capsys, repo, name)

    before = _ledger_state(repo)

    legacy_row = _json_command(capsys, repo, ["lookup", "task36"])
    assert set(legacy_row) == ROW_FIELDS
    assert legacy_row["id"] == "TASK-1"
    assert legacy_row["name"] == "Legacy target"
    assert "TASK-36" not in json.dumps(legacy_row)

    current_row = _json_command(capsys, repo, ["lookup", "TASK-36"])
    assert current_row["id"] == "TASK-36"
    assert current_row["name"] == "Task 36"

    unknown = _json_command(capsys, repo, ["lookup", "36"], expected_rc=1)
    assert unknown["status"] == "FAIL"
    assert len(unknown["issues"]) == 1
    assert unknown["issues"][0]["code"] == "ERR_UNREGISTERED_ENTITY"
    assert unknown["issues"][0]["entity"] == "36"
    assert _ledger_state(repo) == before


def test_update_json_and_stale_expected_status_preserves_prior_change(
    isolated_git_repo: Path, capsys
) -> None:
    repo = isolated_git_repo
    _allocate(capsys, repo, "Status transition", status="READY", note="initial note")

    updated = _json_command(
        capsys,
        repo,
        [
            "update",
            "TASK-1",
            "--status",
            "IN_PROGRESS",
            "--note",
            "first change",
            "--expected-status",
            "READY",
        ],
    )
    assert set(updated) == ROW_FIELDS
    assert updated["id"] == "TASK-1"
    assert updated["status"] == "IN_PROGRESS"
    assert updated["note"] == "first change"

    after_first_update = _ledger_state(repo)
    conflict = _json_command(
        capsys,
        repo,
        [
            "update",
            "TASK-1",
            "--status",
            "DONE",
            "--note",
            "stale overwrite",
            "--expected-status",
            "READY",
        ],
        expected_rc=1,
    )
    assert conflict["status"] == "FAIL"
    assert conflict["issues"][0]["code"] == "ERR_UPDATE_CONFLICT"
    assert conflict["issues"][0]["entity"] == "TASK-1"
    assert _ledger_state(repo) == after_first_update

    current = _json_command(capsys, repo, ["lookup", "TASK-1"])
    assert current["status"] == "IN_PROGRESS"
    assert current["note"] == "first change"


def test_check_legacy_failure_leaves_registry_and_config_untouched(
    isolated_git_repo: Path, capsys
) -> None:
    repo = isolated_git_repo
    _allocate(capsys, repo, "Legacy target", legacy="task36")
    stale_reference = repo / "stale.md"
    stale_reference.write_text("Historical reference: task36\n", encoding="utf-8")
    _git(repo, "add", "stale.md")

    before = _ledger_state(repo)
    body_before = stale_reference.read_bytes()
    report = _json_command(capsys, repo, ["check-legacy"], expected_rc=1)

    assert report["status"] == "FAIL"
    assert report["issues"][0]["code"] == "ERR_RETIRED_CODE"
    assert report["issues"][0]["entity"] == "TASK-1"
    assert _ledger_state(repo) == before
    assert stale_reference.read_bytes() == body_before

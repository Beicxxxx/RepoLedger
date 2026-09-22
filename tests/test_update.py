"""Tests for safe, locked status and note updates."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import threading

import pytest

from repo_ledger.cli import main
from repo_ledger.config import LedgerConfig
from repo_ledger.errors import LedgerError
from repo_ledger.registry import EntityRegistry


@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    (tmp_path / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
    subprocess.run(["git", "add", "proposal.md"], check=True, capture_output=True)
    return tmp_path


def registry(root: Path):
    config = LedgerConfig.load(root / "ledger.toml")
    return EntityRegistry.load(root / config.registry_path, config)


def test_update_preserves_identity_and_escapes_note(repo):
    reg = registry(repo)
    first = reg.allocate("TASK", "Primary | task \\ name", anchor="proposal.md",
                         legacy="OLD-TASK-1", note="old | note \\ value")
    reg.allocate("TASK", "Related task", anchor="proposal.md", parent=first.id,
                 supersedes=first.id)
    before = registry(repo).lookup(first.id)
    state_path = repo / ".git" / "repo-ledger-serials.json"
    state_before = state_path.read_bytes()

    updated = reg.update(first.id, status="DONE", note="new | note \\ value")

    after = registry(repo).lookup(first.id)
    assert updated.id == first.id
    assert updated.status == "DONE"
    assert updated.note == "new | note \\ value"
    for field in ("id", "name", "parent", "order", "anchor", "supersedes", "date", "legacy"):
        assert getattr(after, field) == getattr(before, field)
    text = (repo / ".ledger" / "ENTITY_REGISTRY.md").read_text(encoding="utf-8")
    assert r"new \| note \\ value" in text
    assert state_path.read_bytes() == state_before


def test_empty_note_is_an_update(repo):
    reg = registry(repo)
    reg.allocate("TASK", "Task", anchor="proposal.md", note="old")

    updated = reg.update("TASK-1", note="")

    assert updated.note == ""
    assert registry(repo).lookup("TASK-1").note == ""


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({}, "ERR_NO_UPDATE"),
        ({"status": "NOT_A_STATUS"}, "ERR_INVALID_STATUS"),
        ({"note": " trailing"}, "ERR_INVALID_FIELD"),
        ({"note": "line\nfeed"}, "ERR_INVALID_FIELD"),
        ({"status": "DONE", "expected_status": "DONE"}, "ERR_UPDATE_CONFLICT"),
    ],
)
def test_invalid_or_conflicting_update_does_not_write(repo, kwargs, code):
    reg = registry(repo)
    reg.allocate("TASK", "Task", anchor="proposal.md")
    before = reg.path.read_bytes()

    with pytest.raises(LedgerError) as error:
        reg.update("TASK-1", **kwargs)

    assert error.value.issue.code == code
    assert reg.path.read_bytes() == before


def test_update_requires_current_id_and_known_entity(repo):
    reg = registry(repo)
    reg.allocate("TASK", "Task", anchor="proposal.md", legacy="OLD-TASK-1")
    before = reg.path.read_bytes()

    with pytest.raises(LedgerError) as legacy_error:
        reg.update("OLD-TASK-1", note="must not mutate")
    assert legacy_error.value.issue.code == "ERR_LEGACY_READONLY"

    with pytest.raises(LedgerError) as unknown_error:
        reg.update("TASK-999", note="must not mutate")
    assert unknown_error.value.issue.code == "ERR_UNREGISTERED_ENTITY"
    assert reg.path.read_bytes() == before


def test_update_reads_latest_config_status_vocabulary(repo):
    reg = registry(repo)
    reg.allocate("TASK", "Task", anchor="proposal.md")
    config_path = repo / "ledger.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + '\n[types.TASK]\nallowed_statuses = ["BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE", "DROPPED", "REVIEW"]\n',
        encoding="utf-8",
    )

    updated = reg.update("TASK-1", status="REVIEW")

    assert updated.status == "REVIEW"
    assert registry(repo).lookup("TASK-1").status == "REVIEW"


def test_update_rejects_latest_config_registry_path_change(repo):
    reg = registry(repo)
    reg.allocate("TASK", "Task", anchor="proposal.md")
    path = repo / "ledger.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'registry_path = ".ledger/ENTITY_REGISTRY.md"',
            'registry_path = ".ledger/OTHER_REGISTRY.md"',
        ),
        encoding="utf-8",
    )
    before = reg.path.read_bytes()

    with pytest.raises(LedgerError) as error:
        reg.update("TASK-1", note="must not target a stale path")

    assert error.value.issue.code == "ERR_REGISTRY_PATH_CHANGED"
    assert reg.path.read_bytes() == before


def test_racing_expected_status_updates_have_one_winner(repo):
    registry(repo).allocate("TASK", "Task", anchor="proposal.md")
    left = registry(repo)
    right = registry(repo)
    state_path = repo / ".git" / "repo-ledger-serials.json"
    state_before = state_path.read_bytes()
    ready = threading.Barrier(2)

    def update(reg, next_status):
        ready.wait()
        try:
            return ("ok", reg.update("TASK-1", status=next_status,
                                      expected_status="BACKLOG").status)
        except LedgerError as error:
            return ("error", error.issue.code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(update, left, "DONE"), pool.submit(update, right, "IN_PROGRESS")]
        results = [future.result() for future in futures]

    assert sorted(results) == [("error", "ERR_UPDATE_CONFLICT"),
                               ("ok", next(status for kind, status in results if kind == "ok"))]
    final = registry(repo)
    assert len(final.rows) == 1
    assert final.lookup("TASK-1").status in {"DONE", "IN_PROGRESS"}
    assert state_path.read_bytes() == state_before


def test_update_rejects_missing_anchor_without_writing(repo):
    reg = registry(repo)
    reg.allocate("TASK", "Task", anchor="proposal.md")
    reg.path.write_text(
        reg.path.read_text(encoding="utf-8").replace("proposal.md", "missing.md"),
        encoding="utf-8",
    )
    before = reg.path.read_bytes()

    with pytest.raises(LedgerError) as error:
        reg.update("TASK-1", status="DONE")

    assert error.value.issue.code == "ERR_ANCHOR_NOT_FOUND"
    assert reg.path.read_bytes() == before


def test_concurrent_update_and_allocate_preserve_both_rows(repo):
    initial = registry(repo)
    initial.allocate("TASK", "Initial", anchor="proposal.md")
    updater = registry(repo)
    allocator = registry(repo)
    ready = threading.Barrier(2)

    def update():
        ready.wait()
        return updater.update("TASK-1", status="DONE", note="updated")

    def allocate():
        ready.wait()
        return allocator.allocate("TASK", "Concurrent", anchor="proposal.md")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(update), pool.submit(allocate)]
        [future.result() for future in futures]

    result = registry(repo)
    assert [row.id for row in result.rows] == ["TASK-1", "TASK-2"]
    assert result.lookup("TASK-1").status == "DONE"
    assert result.lookup("TASK-1").note == "updated"
    assert result.lookup("TASK-2").name == "Concurrent"


def test_concurrent_independent_status_and_note_updates_do_not_clobber(repo):
    registry(repo).allocate("TASK", "Task", anchor="proposal.md")
    status_registry = registry(repo)
    note_registry = registry(repo)
    ready = threading.Barrier(2)

    def update_status():
        ready.wait()
        return status_registry.update("TASK-1", status="DONE")

    def update_note():
        ready.wait()
        return note_registry.update("TASK-1", note="independent note")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(update_status), pool.submit(update_note)]
        [future.result() for future in futures]

    row = registry(repo).lookup("TASK-1")
    assert row.status == "DONE"
    assert row.note == "independent note"


def test_update_rejects_linked_worktree(repo):
    registry(repo).allocate("TASK", "Task", anchor="proposal.md")
    subprocess.run(["git", "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "commit", "-m", "fixture"],
        check=True,
        capture_output=True,
    )
    linked = repo.parent / "linked-update"
    subprocess.run(["git", "worktree", "add", "--detach", str(linked)], check=True, capture_output=True)

    with pytest.raises(LedgerError) as error:
        registry(linked).update("TASK-1", note="must stay in main worktree")

    assert error.value.issue.code == "ERR_ALLOCATION_WORKTREE"

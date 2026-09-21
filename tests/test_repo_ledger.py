"""Comprehensive unit tests for RepoLedger core, CLI, allocator, and linter."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from repo_ledger.cli import main
from repo_ledger.config import LedgerConfig
from repo_ledger.linter import lint_all
from repo_ledger.registry import EntityRegistry


def test_init_and_allocate_lifecycle(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # 1. Run init
    rc = main(["init"])
    assert rc == 0
    assert (tmp_path / "ledger.toml").is_file()
    assert (tmp_path / ".ledger" / "ENTITY_REGISTRY.md").is_file()

    # 2. Allocate TASK-1
    test_file = tmp_path / "src" / "worker.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("# Initial worker\n", encoding="utf-8")

    rc = main(["allocate", "TASK", "First Task", "--owner", "src/worker.py", "--status", "DONE"])
    assert rc == 0

    # 3. Allocate TASK-2 with parent TASK-1
    rc = main(["allocate", "TASK", "Second Task", "--owner", "src/worker.py", "--parent", "TASK-1", "--status", "IN_PROGRESS"])
    assert rc == 0

    # Verify registry content
    config = LedgerConfig.load(tmp_path / "ledger.toml")
    registry = EntityRegistry.load(tmp_path / ".ledger" / "ENTITY_REGISTRY.md", config)
    assert len(registry.rows) == 2
    assert registry.rows[0].id == "TASK-1"
    assert registry.rows[1].id == "TASK-2"
    assert registry.rows[1].parent == "TASK-1"

    # 4. Check passes
    rc = main(["check", "--root", str(tmp_path)])
    assert rc == 0


def test_linter_catches_unregistered_reference(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])

    # Create tracked file mentioning registered TASK-1 and UNREGISTERED TASK-99
    code = tmp_path / "app.py"
    code.write_text("""
def run():
    # Resolves TASK-1
    # Blocked by TASK-99
    pass
""", encoding="utf-8")

    main(["allocate", "TASK", "Task One", "--owner", "app.py", "--status", "DONE"])

    config = LedgerConfig.load(tmp_path / "ledger.toml")
    registry = EntityRegistry.load(tmp_path / ".ledger" / "ENTITY_REGISTRY.md", config)
    issues = lint_all(tmp_path, registry)

    # Must catch TASK-99
    assert len(issues) == 1
    assert "app.py:4" in issues[0].location
    assert "TASK-99" in issues[0].message


def test_linter_catches_serial_gap(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])

    src = tmp_path / "test.py"
    src.write_text("# code\n", encoding="utf-8")

    # Manually create TASK-1 and TASK-3 (skipping TASK-2)
    config = LedgerConfig.load(tmp_path / "ledger.toml")
    reg_path = tmp_path / ".ledger" / "ENTITY_REGISTRY.md"
    registry = EntityRegistry.load(reg_path, config)
    registry.allocate("TASK", "Task 1", owner="test.py", status="DONE")
    r3 = registry.allocate("TASK", "Task 3", owner="test.py", status="DONE")
    r3.id = "TASK-3"  # force gap
    registry.save()

    issues = lint_all(tmp_path, registry)
    gap_issues = [i for i in issues if "gap" in i.message]
    assert len(gap_issues) == 1
    assert "[2]" in gap_issues[0].message


def test_linter_catches_invalid_status(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])

    src = tmp_path / "test.py"
    src.write_text("# code\n", encoding="utf-8")

    config = LedgerConfig.load(tmp_path / "ledger.toml")
    reg_path = tmp_path / ".ledger" / "ENTITY_REGISTRY.md"
    registry = EntityRegistry.load(reg_path, config)
    registry.allocate("TASK", "Task 1", owner="test.py", status="TOTALLY_INVALID_STATUS")
    registry.save()

    issues = lint_all(tmp_path, registry)
    status_issues = [i for i in issues if "status 'TOTALLY_INVALID_STATUS'" in i.message]
    assert len(status_issues) == 1


def test_tree_command(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["init"])

    src = tmp_path / "test.py"
    src.write_text("# code\n", encoding="utf-8")

    main(["allocate", "TASK", "Root Task", "--owner", "test.py", "--status", "DONE"])
    main(["allocate", "TASK", "Child Task", "--owner", "test.py", "--parent", "TASK-1", "--status", "IN_PROGRESS"])

    rc = main(["tree"])
    assert rc == 0

    captured = capsys.readouterr()
    assert "Root Task" in captured.out
    assert "Child Task" in captured.out
    assert "TASK-1" in captured.out
    assert "TASK-2" in captured.out

"""Comprehensive unit tests for RepoLedger core, CLI, allocator, lookup, and linter."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
import pytest

from repo_ledger.cli import main
from repo_ledger.config import LedgerConfig
from repo_ledger.linter import lint_all
from repo_ledger.registry import EntityRegistry


@pytest.fixture(autouse=True)
def git_repository(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)


def track():
    subprocess.run(["git", "add", "."], check=True, capture_output=True)


def test_init_allocate_and_lookup_lifecycle(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    # 1. Run init
    rc = main(["init"])
    assert rc == 0
    assert (tmp_path / "ledger.toml").is_file()
    assert (tmp_path / ".ledger" / "ENTITY_REGISTRY.md").is_file()

    # 2. Allocate TASK-1 with anchor
    doc_file = tmp_path / "docs" / "proposal.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text("# Proposal doc\n", encoding="utf-8")
    track()

    rc = main(["allocate", "TASK", "First Task", "--anchor", "docs/proposal.md", "--status", "DONE"])
    assert rc == 0

    # 3. Lookup TASK-1 in text format
    rc = main(["lookup", "TASK-1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ID:         TASK-1" in out
    assert "Anchor:     docs/proposal.md" in out

    # 4. Lookup TASK-1 in JSON format
    rc = main(["lookup", "TASK-1", "--json"])
    assert rc == 0
    out_json = json.loads(capsys.readouterr().out)
    assert out_json["id"] == "TASK-1"
    assert out_json["name"] == "First Task"
    assert out_json["anchor"] == "docs/proposal.md"

    # 5. Lookup non-existent entity
    rc = main(["lookup", "TASK-999"])
    assert rc == 1

    # 6. Check passes cleanly
    rc = main(["check", "--root", str(tmp_path)])
    assert rc == 0


def test_linter_catches_unregistered_reference_with_stable_code(tmp_path: Path, monkeypatch, capsys):
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

    track()
    main(["allocate", "TASK", "Task One", "--anchor", "app.py", "--status", "DONE"])
    capsys.readouterr()  # clear buffer

    # Run check with --json
    rc = main(["check", "--root", str(tmp_path), "--json"])
    assert rc == 1

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "FAIL"
    issues = report["issues"]
    assert len(issues) == 1
    assert issues[0]["code"] == "ERR_UNREGISTERED_ENTITY"
    assert issues[0]["entity"] == "TASK-99"
    assert "app.py:4" in issues[0]["location"]


def test_serial_gaps_not_errors_by_default(tmp_path: Path, monkeypatch):
    """Per RFC constraint: serial gaps are not errors by default."""
    monkeypatch.chdir(tmp_path)
    main(["init"])

    src = tmp_path / "test.py"
    src.write_text("# code\n", encoding="utf-8")
    track()

    config = LedgerConfig.load(tmp_path / "ledger.toml")
    assert config.allow_gaps is True

    reg_path = tmp_path / ".ledger" / "ENTITY_REGISTRY.md"
    registry = EntityRegistry.load(reg_path, config)
    registry.allocate("TASK", "Task 1", anchor="test.py", status="DONE")
    r3 = registry.allocate("TASK", "Task 3", anchor="test.py", status="DONE")
    r3.id = "TASK-3"  # force gap
    r3.order = "3"
    registry.save()

    # Gap exists, but allow_gaps=True -> no error!
    issues = lint_all(tmp_path, registry)
    gap_issues = [i for i in issues if i.code == "ERR_SERIAL_GAP"]
    assert len(gap_issues) == 0


def test_linter_catches_missing_anchor(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])

    config = LedgerConfig.load(tmp_path / "ledger.toml")
    reg_path = tmp_path / ".ledger" / "ENTITY_REGISTRY.md"
    registry = EntityRegistry.load(reg_path, config)
    src = tmp_path / "evidence.md"
    src.write_text("Evidence\n", encoding="utf-8")
    track()
    registry.allocate("TASK", "Task 1", anchor="evidence.md", status="DONE")
    registry.rows[0].anchor = "non_existent_file.py"
    registry.save()

    issues = lint_all(tmp_path, registry)
    anchor_issues = [i for i in issues if i.code == "ERR_ANCHOR_NOT_FOUND"]
    assert len(anchor_issues) == 1
    assert "non_existent_file.py" in anchor_issues[0].reason


def test_tree_command(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["init"])

    src = tmp_path / "test.py"
    src.write_text("# code\n", encoding="utf-8")
    track()

    main(["allocate", "TASK", "Root Task", "--anchor", "test.py", "--status", "DONE"])
    main(["allocate", "TASK", "Child Task", "--anchor", "test.py", "--parent", "TASK-1", "--status", "IN_PROGRESS"])

    rc = main(["tree"])
    assert rc == 0

    captured = capsys.readouterr()
    assert "Root Task" in captured.out
    assert "Child Task" in captured.out
    assert "TASK-1" in captured.out
    assert "TASK-2" in captured.out

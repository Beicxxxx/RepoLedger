"""Regression tests for the independent-order switch (order as a render-only plan position)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from repo_ledger.cli import main
from repo_ledger.config import LedgerConfig
from repo_ledger.errors import LedgerError
from repo_ledger.registry import EntityRegistry


def write_config(root, independent_order):
    text = '[ledger]\nschema_version = "1.0"\nallow_gaps = true\n'
    if independent_order is not None:
        text += f"independent_order = {'true' if independent_order else 'false'}\n"
    (root / "ledger.toml").write_text(text, encoding="utf-8")


def enable_unique_order(root):
    path = root / "ledger.toml"
    path.write_text(path.read_text(encoding="utf-8") + "unique_order_within_scope = true\n",
                    encoding="utf-8")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
    subprocess.run(["git", "add", "proposal.md"], check=True, capture_output=True)
    return tmp_path


def registry(root):
    config = LedgerConfig.load(root / "ledger.toml")
    return EntityRegistry.load(root / config.registry_path, config)


def prepare(root, independent_order):
    assert main(["init"]) == 0
    write_config(root, independent_order)
    return registry(root)


def test_default_mode_keeps_order_equal_to_serial(repo):
    reg = prepare(repo, None)
    reg.allocate("TASK", "First", anchor="proposal.md")
    reg.allocate("TASK", "Second", anchor="proposal.md")

    assert [row.order for row in registry(repo).rows] == ["1", "2"]
    with pytest.raises(LedgerError) as error:
        registry(repo).allocate("TASK", "Third", anchor="proposal.md", order="5")
    assert error.value.issue.code == "ERR_ORDER_FIXED"


def test_default_mode_rejects_hand_edited_order(repo):
    reg = prepare(repo, None)
    reg.allocate("TASK", "First", anchor="proposal.md")
    original = reg.path.read_text(encoding="utf-8")
    edited = original.replace("| 1 | proposal.md |", "| 7 | proposal.md |")
    assert edited != original
    reg.path.write_text(edited, encoding="utf-8")

    with pytest.raises(LedgerError) as error:
        registry(repo)
    assert error.value.issue.code == "ERR_INVALID_FIELD"


def test_sibling_scope_restarts_per_parent_and_type(repo):
    reg = prepare(repo, True)
    parent = reg.allocate("TASK", "Parent", anchor="proposal.md")
    first = reg.allocate("TASK", "Child A", anchor="proposal.md", parent=parent.id)
    second = reg.allocate("TASK", "Child B", anchor="proposal.md", parent=parent.id)
    other = reg.allocate("TASK", "Parent Two", anchor="proposal.md")
    nested = reg.allocate("TASK", "Child C", anchor="proposal.md", parent=other.id)
    issue = reg.allocate("ISSUE", "Sibling issue", anchor="proposal.md", parent=parent.id)

    assert (parent.order, other.order) == ("1", "2")
    assert (first.order, second.order) == ("1", "2")
    assert nested.order == "1"
    assert issue.order == "1"
    # Ledger rows stay append-only in serial order; only the order column carries plan position.
    assert [row.id for row in registry(repo).rows] == [
        "TASK-1", "TASK-2", "TASK-3", "TASK-4", "TASK-5", "ISSUE-1"]
    assert main(["check", "--json"]) == 0


def test_plan_position_is_independent_of_identity_and_status(repo):
    reg = prepare(repo, True)
    row = reg.allocate("TASK", "Inserted later", anchor="proposal.md", order="9", status="READY")

    assert (row.id, row.order, row.status) == ("TASK-1", "9", "READY")
    assert registry(repo).lookup("TASK-1").order == "9"
    assert main(["check", "--json"]) == 0


def test_same_order_allowed_in_different_parent_scopes(repo):
    reg = prepare(repo, True)
    parent_a = reg.allocate("TASK", "Parent A", anchor="proposal.md")
    parent_b = reg.allocate("TASK", "Parent B", anchor="proposal.md")
    child_a = reg.allocate("TASK", "Child A", anchor="proposal.md", parent=parent_a.id, order="1")
    child_b = reg.allocate("TASK", "Child B", anchor="proposal.md", parent=parent_b.id, order="1")

    assert (child_a.order, child_b.order) == ("1", "1")
    assert main(["check", "--json"]) == 0


@pytest.mark.parametrize("value", ["0", "007", "-1", "abc", "1.0", ""])
def test_invalid_order_values_are_rejected_without_writing(repo, value):
    reg = prepare(repo, True)
    before = reg.path.read_bytes()

    with pytest.raises(LedgerError) as error:
        registry(repo).allocate("TASK", "Bad order", anchor="proposal.md", order=value)

    assert error.value.issue.code == "ERR_INVALID_ORDER"
    assert registry(repo).path.read_bytes() == before


def test_duplicate_order_is_fail_closed(repo):
    reg = prepare(repo, True)
    enable_unique_order(repo)
    reg = registry(repo)
    reg.allocate("TASK", "First", anchor="proposal.md", order="1")
    reg.allocate("TASK", "Second", anchor="proposal.md", order="2")

    with pytest.raises(LedgerError) as allocate_error:
        registry(repo).allocate("TASK", "Third", anchor="proposal.md", order="2")
    assert allocate_error.value.issue.code == "ERR_DUPLICATE_ORDER"

    original = reg.path.read_text(encoding="utf-8")
    edited = original.replace("| TASK-2 | Second | BACKLOG |  | 2 |", "| TASK-2 | Second | BACKLOG |  | 1 |")
    assert edited != original
    reg.path.write_text(edited, encoding="utf-8")
    with pytest.raises(LedgerError) as load_error:
        registry(repo)
    assert load_error.value.issue.code == "ERR_DUPLICATE_ORDER"


def test_update_can_replan_order_and_still_rejects_collisions(repo, capsys):
    reg = prepare(repo, True)
    enable_unique_order(repo)
    reg = registry(repo)
    first = reg.allocate("TASK", "First", anchor="proposal.md")
    second = reg.allocate("TASK", "Second", anchor="proposal.md")
    capsys.readouterr()

    assert main(["update", second.id, "--order", "1", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["issues"][0]["code"] == "ERR_DUPLICATE_ORDER"
    assert main(["update", first.id, "--order", "3", "--json"]) == 0
    assert main(["update", second.id, "--order", "1", "--json"]) == 0

    rows = {row.id: row for row in registry(repo).rows}
    assert (rows[first.id].order, rows[second.id].order) == ("3", "1")
    assert rows[first.id].status == "BACKLOG"
    assert rows[first.id].legacy == "" and rows[first.id].anchor == "proposal.md"


def test_update_order_rejected_when_switch_is_off(repo, capsys):
    reg = prepare(repo, None)
    row = reg.allocate("TASK", "First", anchor="proposal.md")
    capsys.readouterr()

    assert main(["update", row.id, "--order", "4", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["issues"][0]["code"] == "ERR_ORDER_FIXED"
    assert registry(repo).lookup(row.id).order == "1"


def test_enabling_switch_accepts_existing_serial_orders(repo):
    reg = prepare(repo, None)
    reg.allocate("TASK", "First", anchor="proposal.md")
    reg.allocate("TASK", "Second", anchor="proposal.md")

    write_config(repo, True)

    assert [row.order for row in registry(repo).rows] == ["1", "2"]
    assert main(["check", "--json"]) == 0


def test_tree_renders_plan_order_not_serial_order(repo, capsys):
    reg = prepare(repo, True)
    parent = reg.allocate("TASK", "Parent", anchor="proposal.md")
    later = reg.allocate("TASK", "Later serial", anchor="proposal.md", parent=parent.id, order="2")
    earlier = reg.allocate("TASK", "Earlier plan", anchor="proposal.md", parent=parent.id, order="1")
    capsys.readouterr()

    assert (later.id, earlier.id) == ("TASK-2", "TASK-3")
    assert main(["tree"]) == 0
    children = [line for line in capsys.readouterr().out.splitlines()
                if "Earlier plan" in line or "Later serial" in line]
    assert "Earlier plan" in children[0] and "order=1" in children[0]
    assert "Later serial" in children[1] and "order=2" in children[1]


def test_legacy_guard_stays_aggregated_under_independent_order(repo, capsys):
    reg = prepare(repo, True)
    reg.allocate("TASK", "Retired code owner", anchor="proposal.md", legacy="oldcode")
    (repo / "note.md").write_text("Historical: oldcode\n", encoding="utf-8")
    subprocess.run(["git", "add", "note.md"], check=True, capture_output=True)
    capsys.readouterr()

    assert main(["check-legacy", "--json"]) == 1
    assert "ERR_RETIRED_CODE" in capsys.readouterr().out
    assert main(["check", "--json"]) == 1
    assert "ERR_RETIRED_CODE" in capsys.readouterr().out


def test_config_rejects_non_boolean_switch(repo):
    prepare(repo, None)
    (repo / "ledger.toml").write_text('[ledger]\nindependent_order = "yes"\n', encoding="utf-8")

    with pytest.raises(LedgerError) as error:
        LedgerConfig.load(repo / "ledger.toml")
    assert error.value.issue.code == "ERR_CONFIG"


def test_config_rejects_non_boolean_unique_order_switch(repo):
    prepare(repo, None)
    (repo / "ledger.toml").write_text(
        '[ledger]\nindependent_order = true\nunique_order_within_scope = 1\n', encoding="utf-8")

    with pytest.raises(LedgerError) as error:
        LedgerConfig.load(repo / "ledger.toml")
    assert error.value.issue.code == "ERR_CONFIG"

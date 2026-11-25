"""Parent relations made visible: lookup --ref/--relations, tree views, search, update --parent."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from repo_ledger.cli import main
from repo_ledger.config import LedgerConfig
from repo_ledger.errors import LedgerError
from repo_ledger.linter import scan
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


def family(root):
    reg = registry(root)
    reg.allocate("TASK", "Paper", anchor="proposal.md")                    # TASK-1
    reg.allocate("TASK", "Reviews", anchor="proposal.md", parent="TASK-1")  # TASK-2
    reg.allocate("TASK", "Rerun", anchor="proposal.md", parent="TASK-2")    # TASK-3
    reg.allocate("DECISION", "Pick venue", anchor="proposal.md", parent="TASK-2",
                 status="IN_FORCE")                                            # DECISION-1
    reg.allocate("TASK", "Other", anchor="proposal.md")                     # TASK-4
    return registry(root)


def registry_bytes(root):
    return (root / ".ledger" / "ENTITY_REGISTRY.md").read_bytes()


def test_lookup_ref_names_the_direct_parent(repo, capsys):
    family(repo)
    assert main(["lookup", "TASK-3", "--ref"]) == 0
    assert capsys.readouterr().out == "TASK-3 Rerun（↳ TASK-2 Reviews）\n"
    assert main(["lookup", "TASK-1", "--ref"]) == 0
    assert capsys.readouterr().out == "TASK-1 Paper\n"
    assert main(["lookup", "TASK-3", "--ref", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"id": "TASK-3",
                                                   "ref": "TASK-3 Rerun（↳ TASK-2 Reviews）"}


def test_lookup_text_shows_parent_path_and_children(repo, capsys):
    family(repo)
    assert main(["lookup", "TASK-3"]) == 0
    out = capsys.readouterr().out
    assert "Parent:     TASK-2 Reviews" in out
    assert "Path:       TASK-1 > TASK-2 > TASK-3" in out
    assert main(["lookup", "TASK-2"]) == 0
    out = capsys.readouterr().out
    assert "Children:   2" in out
    # Declared type order first (TASK before DECISION), whatever the allocation order.
    assert out.index("TASK-3 [BACKLOG] Rerun") < out.index("DECISION-1 [IN_FORCE] Pick venue")


def test_lookup_json_keeps_registry_fields_unless_relations_requested(repo, capsys):
    family(repo)
    assert main(["lookup", "TASK-2", "--json"]) == 0
    plain = json.loads(capsys.readouterr().out)
    assert "ancestors" not in plain and "children" not in plain
    assert main(["lookup", "TASK-3", "--json", "--relations"]) == 0
    rich = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rich["ancestors"]] == ["TASK-1", "TASK-2"]
    assert rich["children"] == []


def test_long_note_is_cut_in_text_lookup_only(repo, capsys):
    reg = registry(repo)
    reg.allocate("TASK", "Long", anchor="proposal.md", note="x" * 1000)
    assert main(["lookup", "TASK-1"]) == 0
    assert "(1000 characters; --json prints all)" in capsys.readouterr().out
    assert main(["lookup", "TASK-1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["note"] == "x" * 1000


def test_tree_root_type_and_json(repo, capsys):
    family(repo)
    assert main(["tree", "TASK-2"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "^ TASK-1 [BACKLOG] Paper"
    assert "TASK-4" not in out and "TASK-3" in out and "DECISION-1" in out
    assert main(["tree", "--type", "DECISION"]) == 0
    assert capsys.readouterr().out == ""  # DECISION-1 is not top level
    assert main(["tree", "--json", "TASK-1"]) == 0
    tree = json.loads(capsys.readouterr().out)
    assert tree[0]["id"] == "TASK-1"
    assert [c["id"] for c in tree[0]["children"][0]["children"]] == ["TASK-3", "DECISION-1"]
    assert main(["tree", "TASK-99"]) == 1


def test_tree_sorts_ids_by_number_and_types_by_declaration(repo, capsys):
    reg = registry(repo)
    for name in ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"):
        reg.allocate("TASK", name, anchor="proposal.md")
    reg.allocate("ISSUE", "bug", anchor="proposal.md")
    assert main(["tree"]) == 0
    ids = [line.split()[0] for line in capsys.readouterr().out.splitlines()]
    assert ids[:3] == ["TASK-1", "TASK-2", "TASK-3"]
    assert ids.index("TASK-11") == 10
    assert ids[-1] == "ISSUE-1"


def test_tree_hides_inactive_decisions_unless_all(repo, capsys):
    path = repo / "ledger.toml"
    path.write_text(path.read_text(encoding="utf-8").replace("[legacy_guard]",
        '[types.TASK]\nallowed_statuses = ["BACKLOG", "DONE"]\n\n'
        '[types.DECISION]\nallowed_statuses = ["ACTIVE", "RETIRED"]\n\n[legacy_guard]'),
        encoding="utf-8")
    reg = registry(repo)
    reg.allocate("DECISION", "Old rule", anchor="proposal.md", status="RETIRED")
    assert main(["tree"]) == 0
    assert "DECISION-1" not in capsys.readouterr().out
    assert main(["tree", "--all"]) == 0
    assert "DECISION-1" in capsys.readouterr().out


def test_search_text_shows_parent(repo, capsys):
    family(repo)
    assert main(["search", "Rerun"]) == 0
    assert "TASK-3 [BACKLOG] Rerun (↳ TASK-2)" in capsys.readouterr().out


def test_update_parent_moves_keeps_id_and_detaches(repo, capsys):
    family(repo)
    assert main(["update", "TASK-3", "--parent", "TASK-4", "--json"]) == 0
    moved = json.loads(capsys.readouterr().out)
    assert (moved["id"], moved["parent"], moved["name"]) == ("TASK-3", "TASK-4", "Rerun")
    assert registry(repo).lookup("TASK-3").parent == "TASK-4"
    assert main(["update", "TASK-3", "--parent", ""]) == 0
    assert registry(repo).lookup("TASK-3").parent == ""


@pytest.mark.parametrize("parent, code", [
    ("TASK-3", "ERR_RELATION_CYCLE"),       # TASK-1 under its own grandchild
    ("TASK-1", "ERR_SELF_REFERENCE"),
    ("TASK-99", "ERR_RELATION_NOT_FOUND"),
    ("TASK-2,TASK-4", "ERR_INVALID_RELATION"),
])
def test_bad_parent_update_writes_nothing(repo, parent, code):
    family(repo)
    before = registry_bytes(repo)
    with pytest.raises(LedgerError) as raised:
        registry(repo).update("TASK-1", parent=parent)
    assert raised.value.issue.code == code
    assert registry_bytes(repo) == before


def test_update_parent_takes_next_free_order_with_independent_order(repo):
    path = repo / "ledger.toml"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "independent_order = false", "independent_order = true"), encoding="utf-8")
    family(repo)
    reg = registry(repo)
    reg.allocate("TASK", "Sibling", anchor="proposal.md", parent="TASK-4")  # TASK-5, order 1
    moved = registry(repo).update("TASK-3", parent="TASK-4")
    assert moved.order == "2"
    pinned = registry(repo).update("TASK-3", parent="TASK-1", order="7")
    assert (pinned.parent, pinned.order) == ("TASK-1", "7")


def test_scan_whole_text_keeps_line_columns_and_left_boundary(repo):
    reg = family(repo)
    (repo / "notes.md").write_text(
        "TASK-1 ok\r\nsee  TASK-77 and xTASK-78, -TASK-79, TASK-80x\nTASK-81 TASK-82\n",
        encoding="utf-8")
    subprocess.run(["git", "add", "notes.md"], check=True, capture_output=True)
    issues, _ = scan(repo, reg)
    assert sorted((i.entity, i.location) for i in issues) == [
        ("TASK-77", "notes.md:2:6"), ("TASK-81", "notes.md:3:1"), ("TASK-82", "notes.md:4:1")]

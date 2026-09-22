"""Regression tests for the project 'owner' column layout (anchor under its legacy name)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repo_ledger.cli import main
from repo_ledger.config import LedgerConfig
from repo_ledger.errors import LedgerError
from repo_ledger.registry import (
    CANONICAL_FIELDS,
    OWNER_FIELDS,
    OWNER_TABLE_HEADER,
    TABLE_HEADER,
    EntityRegistry,
)

PREAMBLE = "<!-- schema: 1.0 -->\n# Entity Registry\n\n> owner is the evidence carrier.\n\n"
OWNER_TABLE = (
    "| id | name | status | parent | order | owner | legacy | supersedes | date | note |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    "| TASK-1 | First task | READY |  | 1 | docs/proposal.md | old-code |  | 2026-09-22 | note with max\\|SMD\\| |\n"
    "| TASK-2 | Second task | BACKLOG | TASK-1 | 2 | docs/proposal.md |  | TASK-1 | 2026-09-22 |  |\n"
)
UNKNOWN_TABLE = (
    "| id | name | status | parent | order | owner | supersedes | legacy | date | note |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ledger.toml").write_text(
        '[ledger]\nschema_version = "1.0"\nregistry_path = ".ledger/ENTITY_REGISTRY.md"\n'
        'allow_gaps = true\nindependent_order = true\n', encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/proposal.md").write_text("# Proposal\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/proposal.md"], check=True, capture_output=True)
    return tmp_path


def write_registry(root, text):
    path = root / ".ledger/ENTITY_REGISTRY.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def load(root):
    config = LedgerConfig.load(root / "ledger.toml")
    return EntityRegistry.load(root / config.registry_path, config)


def test_owner_layout_loads_and_maps_owner_to_anchor(repo):
    write_registry(repo, PREAMBLE + OWNER_TABLE)
    registry = load(repo)

    assert registry.table_header == OWNER_TABLE_HEADER
    assert registry.fields == OWNER_FIELDS
    first = registry.lookup("TASK-1")
    assert first.anchor == "docs/proposal.md"
    assert first.legacy == "old-code"
    # Escaped pipe round-trips through the owner layout.
    assert first.note == "note with max|SMD|"
    assert registry.lookup("TASK-2").supersedes == "TASK-1"


def test_owner_layout_is_preserved_on_save_and_update(repo):
    write_registry(repo, PREAMBLE + OWNER_TABLE)
    registry = load(repo)

    registry.update("TASK-1", status="DONE", note="updated")
    text = (repo / ".ledger/ENTITY_REGISTRY.md").read_text(encoding="utf-8")
    assert OWNER_TABLE_HEADER[0] in text
    assert "| id | name | status | parent | order | owner | legacy | supersedes | date | note |" in text
    assert text.count("| id | name | status | parent | order | owner | legacy | supersedes | date | note |") == 1
    assert any(line.startswith("| --- |") for line in text.splitlines())

    reloaded = load(repo)
    assert reloaded.table_header == OWNER_TABLE_HEADER
    assert reloaded.lookup("TASK-1").status == "DONE"
    assert reloaded.lookup("TASK-1").note == "updated"
    assert reloaded.lookup("TASK-1").legacy == "old-code"
    assert reloaded.lookup("TASK-2").supersedes == "TASK-1"


def test_owner_layout_supports_allocation_in_place(repo):
    write_registry(repo, PREAMBLE + OWNER_TABLE)
    registry = load(repo)

    row = registry.allocate("TASK", "Third task", anchor="docs/proposal.md")

    assert row.id == "TASK-3"
    # No parent means the row joins the root scope, where the next free plan position is 2.
    assert row.order == "2"
    assert load(repo).table_header == OWNER_TABLE_HEADER


def test_canonical_layout_stays_canonical(repo):
    write_registry(repo, PREAMBLE + OWNER_TABLE)
    registry = load(repo)
    registry.table_header, registry.fields = list(TABLE_HEADER), CANONICAL_FIELDS
    registry.save()

    reloaded = load(repo)
    assert reloaded.table_header == TABLE_HEADER
    assert reloaded.fields == CANONICAL_FIELDS
    assert reloaded.lookup("TASK-1").anchor == "docs/proposal.md"


def test_unknown_ten_column_header_still_fails(repo):
    write_registry(repo, PREAMBLE + UNKNOWN_TABLE)

    with pytest.raises(LedgerError) as error:
        load(repo)
    assert error.value.issue.code == "ERR_HEADER"

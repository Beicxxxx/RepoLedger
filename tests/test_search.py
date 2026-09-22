"""Tests for read-only literal entity search."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from repo_ledger.config import LedgerConfig
from repo_ledger.errors import LedgerError
from repo_ledger.registry import EntityRegistry, EntityRow
from repo_ledger.search import search_entities


def make_registry():
    return SimpleNamespace(rows=[
        EntityRow("TASK-1", "Alpha [helper]", "READY", order="1", anchor="one.md", legacy="OLD-ALPHA"),
        EntityRow("TASK-2", "Alpha", "DONE", order="2", anchor="two.md"),
        EntityRow("TASK-3", "Other task", "BLOCKED", order="3", anchor="three.md", legacy="alpha"),
        EntityRow("TASK-4", "task-20", "BACKLOG", order="4", anchor="four.md"),
        EntityRow("TASK-5", "中文任务", "READY", order="5", anchor="five.md", legacy="旧任务"),
    ])


def test_search_ranks_exact_alias_then_name_then_substring_and_preserves_ledger_order():
    report = search_entities(make_registry(), "alpha")

    assert report["total"] == 3
    assert [item["id"] for item in report["results"]] == ["TASK-3", "TASK-2", "TASK-1"]


def test_search_is_casefolded_literal_and_returns_only_json_ready_fields():
    registry = make_registry()

    report = search_entities(registry, "TASK-2")
    assert [item["id"] for item in report["results"]] == ["TASK-2", "TASK-4"]
    assert set(report["results"][0]) == {
        "id", "name", "status", "anchor", "parent", "supersedes", "legacy"
    }
    assert json.loads(json.dumps(report))["query"] == "TASK-2"

    literal = search_entities(registry, "[")
    assert literal["total"] == 1
    assert literal["results"][0]["id"] == "TASK-1"


def test_search_handles_chinese_without_normalizing_values():
    report = search_entities(make_registry(), "任务")

    assert report["total"] == 1
    assert [item["id"] for item in report["results"]] == ["TASK-5"]
    assert report["results"][0]["name"] == "中文任务"
    assert report["results"][0]["legacy"] == "旧任务"


def test_search_limit_counts_results_and_does_not_mutate_registry():
    registry = make_registry()
    rows_before = list(registry.rows)
    values_before = [row.__dict__.copy() for row in registry.rows]

    report = search_entities(registry, "task", limit=2)

    assert report["total"] == 5
    assert report["limit"] == 2
    assert len(report["results"]) == 2
    assert registry.rows == rows_before
    assert [row.__dict__ for row in registry.rows] == values_before


@pytest.mark.parametrize("query", ["", "   ", "\t"])
def test_blank_query_is_rejected(query):
    with pytest.raises(LedgerError) as error:
        search_entities(make_registry(), query)
    assert error.value.issue.code == "ERR_SEARCH_QUERY"


@pytest.mark.parametrize("limit", [0, -1, 101, 1.0, True, None])
def test_invalid_limit_is_rejected(limit):
    with pytest.raises(LedgerError) as error:
        search_entities(make_registry(), "task", limit=limit)
    assert error.value.issue.code == "ERR_SEARCH_LIMIT"


def test_malformed_ledger_error_propagates_before_search(tmp_path: Path):
    path = tmp_path / "ENTITY_REGISTRY.md"
    path.write_text(
        """<!-- schema: 1.0 -->
# Entity Registry

| id | name | status | parent | order | anchor | supersedes | date | legacy | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TASK-1 | Valid | READY |  | 1 | proposal.md |  | 2026-09-22 |  |  |
malformed ledger row
""",
        encoding="utf-8",
    )

    with pytest.raises(LedgerError) as error:
        search_entities(EntityRegistry.load(path, LedgerConfig.default()), "valid")
    assert error.value.issue.code == "ERR_ROW_FORMAT"

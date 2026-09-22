"""Regression tests for narrow, declared exemptions of non-registered reference tokens."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from repo_ledger.cli import main
from repo_ledger.config import LedgerConfig
from repo_ledger.errors import LedgerError


EXEMPTION_BLOCK = '''
[reference_exemptions]
"docs/teaching.md" = ["TASK-014"]
"tests/legacy_case.py" = ["TASK-99", "GATE-99"]
'''


@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    (tmp_path / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    subprocess.run(["git", "add", "proposal.md"], check=True, capture_output=True)
    return tmp_path


def configure(root, text):
    (root / "ledger.toml").write_text(
        '[ledger]\nschema_version = "1.0"\nallow_gaps = true\n' + text, encoding="utf-8")


def allocate(root, name, capsys):
    capsys.readouterr()
    assert main(["allocate", "TASK", name, "--anchor", "proposal.md", "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_declared_token_is_suppressed_and_audited(repo, capsys):
    allocate(repo, "Registered task", capsys)
    (repo / "docs/teaching.md").write_text(
        "Counterexample only: TASK-014 is not a real entity.\n", encoding="utf-8")
    configure(repo, EXEMPTION_BLOCK)
    capsys.readouterr()

    assert main(["check", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PASS"
    assert report["scope"]["reference_exemptions"] == {
        "docs/teaching.md": ["TASK-014"], "tests/legacy_case.py": ["TASK-99", "GATE-99"]}
    assert report["scope"]["suppressed"] == [
        {"file": "docs/teaching.md", "line": 1, "column": 22, "token": "TASK-014"}]


def test_exemption_is_scoped_to_file_and_token(repo, capsys):
    allocate(repo, "Registered task", capsys)
    (repo / "docs/teaching.md").write_text(
        "TASK-014 is exempt, TASK-015 is not.\n", encoding="utf-8")
    (repo / "elsewhere.md").write_text("TASK-014 here is not exempt.\n", encoding="utf-8")
    configure(repo, EXEMPTION_BLOCK)
    capsys.readouterr()

    assert main(["check", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    locations = {issue["location"] for issue in report["issues"]}
    assert locations == {"docs/teaching.md:1:21", "elsewhere.md:1:1"}
    assert {issue["entity"] for issue in report["issues"]} == {"TASK-014", "TASK-015"}
    assert [(entry["file"], entry["token"]) for entry in report["scope"]["suppressed"]] == [
        ("docs/teaching.md", "TASK-014")]


def test_undeclared_file_glob_does_not_suppress(repo, capsys):
    allocate(repo, "Registered task", capsys)
    (repo / "docs/teaching.md").write_text("TASK-99\n", encoding="utf-8")
    configure(repo, EXEMPTION_BLOCK)
    capsys.readouterr()

    assert main(["check", "--json"]) == 1
    assert "TASK-99" in json.loads(capsys.readouterr().out)["issues"][0]["entity"]


def test_valid_unknown_reference_without_exemptions_still_fails(repo, capsys):
    allocate(repo, "Registered task", capsys)
    (repo / "docs/teaching.md").write_text("TASK-014\n", encoding="utf-8")
    capsys.readouterr()

    assert main(["check", "--json"]) == 1
    issue = json.loads(capsys.readouterr().out)["issues"][0]
    assert issue["code"] == "ERR_UNREGISTERED_ENTITY"
    assert "exemptions" in issue["suggestion"]


@pytest.mark.parametrize("block", [
    '["docs/x.md"]',
    '[reference_exemptions]\n"../escape.md" = ["TASK-1"]\n',
    '[reference_exemptions]\n"docs/x.md" = ["task-1"]\n',
    '[reference_exemptions]\n"docs/x.md" = ["TASK-1", "TASK-1"]\n',
    '[reference_exemptions]\n"docs/x.md" = []\n',
    '[reference_exemptions]\n"docs/x.md" = ["TASK-.*"]\n',
    '[reference_exemptions]\n"docs/x.md" = "TASK-1"\n',
])
def test_invalid_exemption_config_is_rejected(repo, block, capsys):
    (repo / "ledger.toml").write_text(
        '[ledger]\nschema_version = "1.0"\n' + block, encoding="utf-8")
    capsys.readouterr()

    assert main(["check", "--json"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["issues"][0]["code"] == "ERR_CONFIG"
    assert report["issues"][0]["category"] == "configuration"


def test_exemption_does_not_change_registry_or_suppress_registered_ids(repo, capsys):
    allocate(repo, "Registered task", capsys)
    (repo / "docs/teaching.md").write_text("TASK-1 TASK-2\n", encoding="utf-8")
    configure(repo, EXEMPTION_BLOCK)
    capsys.readouterr()

    assert main(["check", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    # Exemptions never hide registered entities; only TASK-2 is unknown here.
    assert [issue["entity"] for issue in report["issues"]] == ["TASK-2"]
    assert report["scope"]["suppressed"] == []

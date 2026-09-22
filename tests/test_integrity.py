"""Regression tests for the first-release integrity boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

from repo_ledger.cli import main
from repo_ledger.config import LedgerConfig
from repo_ledger.errors import LedgerError
from repo_ledger.registry import EntityRegistry, EntityRow, FileLock, _split_row_cells

@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    (tmp_path / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
    subprocess.run(["git", "add", "proposal.md"], check=True, capture_output=True)
    return tmp_path

def registry(root):
    return EntityRegistry.load(root / ".ledger/ENTITY_REGISTRY.md", LedgerConfig.load(root / "ledger.toml"))

@pytest.mark.parametrize("value", ["中文 max|SMD|", r"one\two", r"\|\\|", "", "a\\", "|", r"literal\n"])
def test_codec_roundtrip(value):
    row = EntityRow("TASK-1", value, "READY", note=value)
    decoded = _split_row_cells(row.to_markdown_row())
    assert decoded[1] == value
    assert decoded[-1] == value

@pytest.mark.parametrize("value", ["a\nb", "a\rb", "a\tb", "a\0b", " trailing", "trailing ", "a\u2028b", "a\x85b"])
def test_unsupported_field_content(value):
    with pytest.raises(LedgerError, match="Fields"):
        EntityRow("TASK-1", value, "READY").to_markdown_row()

@pytest.mark.parametrize("mutation,code", [
    ("missing-schema", "ERR_SCHEMA"), ("unknown-schema", "ERR_SCHEMA"),
    ("short-row", "ERR_COLUMN_COUNT"), ("extra-column", "ERR_COLUMN_COUNT"),
    ("duplicate", "ERR_DUPLICATE_ID"), ("bad-status", "ERR_INVALID_STATUS"),
    ("conflict", "ERR_MERGE_CONFLICT"), ("garbage", "ERR_ROW_FORMAT"),
    ("bad-escape", "ERR_ESCAPE"), ("missing-anchor", "ERR_MISSING_ANCHOR"),
    ("bad-date", "ERR_INVALID_FIELD"),
])
def test_fail_closed(repo, mutation, code):
    reg = registry(repo)
    reg.allocate("TASK", "Valid", anchor="proposal.md")
    text = reg.path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if mutation == "missing-schema":
        lines = lines[1:]
    elif mutation == "unknown-schema":
        lines[0] = "<!-- schema: 2.0 -->"
    elif mutation == "short-row":
        lines[-1] = "| TASK-2 |"
    elif mutation == "extra-column":
        lines[-1] += " extra |"
    elif mutation == "duplicate":
        lines.append(lines[-1])
    elif mutation == "bad-status":
        lines[-1] = lines[-1].replace("BACKLOG", "INVALID")
    elif mutation == "conflict":
        lines.append("<<<<<<< HEAD")
    elif mutation == "garbage":
        lines.append("this record cannot be parsed")
    elif mutation == "bad-escape":
        lines[-1] = lines[-1].replace("Valid", r"bad\q")
    elif mutation == "missing-anchor":
        lines[-1] = lines[-1].replace("proposal.md", "")
    elif mutation == "bad-date":
        lines[-1] = lines[-1].replace(reg.rows[0].date, "tomorrow")
    reg.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    before = reg.path.read_bytes()
    with pytest.raises(LedgerError) as error:
        registry(repo)
    assert error.value.issue.code == code
    assert ":" in error.value.issue.location
    assert main(["check", "--json"]) != 0
    assert before == reg.path.read_bytes()

@pytest.mark.parametrize("anchor,code", [
    ("missing.md", "ERR_ANCHOR_NOT_FOUND"), ("new.md", "ERR_ANCHOR_NOT_FOUND"),
    ("../outside.md", "ERR_UNSAFE_PATH"),
    ("a"*40, "ERR_UNSUPPORTED_ANCHOR"), ("b"*64, "ERR_UNSUPPORTED_ANCHOR"),
    ("HEAD:proposal.md", "ERR_UNSUPPORTED_ANCHOR"), ("", "ERR_MISSING_ANCHOR"),
])
def test_invalid_anchor_does_not_allocate(repo, anchor, code):
    (repo / "new.md").write_text("untracked", encoding="utf-8")
    before = registry(repo).path.read_bytes()
    with pytest.raises(LedgerError) as error:
        registry(repo).allocate("TASK", "Bad anchor", anchor=anchor)
    assert error.value.issue.code == code
    assert registry(repo).path.read_bytes() == before

def test_sequential_and_rollback_highwater(repo):
    reg = registry(repo)
    empty = reg.path.read_bytes()
    assert reg.allocate("TASK", "One", anchor="proposal.md").id == "TASK-1"
    assert reg.allocate("ISSUE", "One", anchor="proposal.md").id == "ISSUE-1"
    reg.path.write_bytes(empty)
    assert registry(repo).allocate("TASK", "After rollback", anchor="proposal.md").id == "TASK-2"

def test_process_concurrency(repo):
    source = str(Path(__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": source}
    processes = [subprocess.Popen([sys.executable, "-m", "repo_ledger", "allocate", "TASK",
                                  f"Worker {i}", "--anchor", "proposal.md", "--json"],
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for i in range(6)]
    ids = []
    for process in processes:
        out, err = process.communicate(timeout=30)
        assert process.returncode == 0, (out, err)
        ids.append(json.loads(out)["id"])
    assert set(ids) == {f"TASK-{i}" for i in range(1, 7)}
    assert len(registry(repo).rows) == 6

def test_lock_timeout(repo):
    path = repo / ".git/repo-ledger-allocate.lock"
    with FileLock(path):
        with pytest.raises(LedgerError) as error:
            with FileLock(path, timeout=.04):
                pass
        assert error.value.issue.code == "ERR_LOCK_TIMEOUT"


def test_failed_registry_write_reserves_number(repo, monkeypatch):
    reg = registry(repo)
    before = reg.path.read_bytes()
    def interrupted():
        raise OSError("simulated interrupted replacement")
    monkeypatch.setattr(reg, "save", interrupted)
    with pytest.raises(OSError):
        reg.allocate("TASK", "Interrupted", anchor="proposal.md")
    assert reg.path.read_bytes() == before
    assert registry(repo).allocate("TASK", "Retry", anchor="proposal.md").id == "TASK-2"


def test_duplicate_legacy_alias_is_rejected(repo):
    reg = registry(repo)
    reg.allocate("TASK", "One", anchor="proposal.md", legacy="OLD-1")
    with pytest.raises(LedgerError) as error:
        reg.allocate("TASK", "Two", anchor="proposal.md", legacy="OLD-1")
    assert error.value.issue.code == "ERR_DUPLICATE_LEGACY"

    reg.allocate("TASK", "Two", anchor="proposal.md")
    reg.rows[1].legacy = "OLD-1"
    reg.save()
    with pytest.raises(LedgerError) as error:
        registry(repo)
    assert error.value.issue.code == "ERR_DUPLICATE_LEGACY"


def test_nine_column_registry_is_readable_and_upgraded(repo):
    path = repo / ".ledger" / "ENTITY_REGISTRY.md"
    path.write_text(
        """<!-- schema: 1.0 -->
# Entity Registry

| id | name | status | parent | order | anchor | supersedes | date | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TASK-1 | Old format | BACKLOG |  | 1 | proposal.md |  | 2026-09-22 | preserved |
""",
        encoding="utf-8")
    loaded = registry(repo)
    assert loaded.lookup("TASK-1").legacy == ""
    assert loaded.lookup("TASK-1").note == "preserved"
    loaded.save()
    text = path.read_text(encoding="utf-8")
    assert "| id | name | status | parent | order | anchor | supersedes | date | legacy | note |" in text
    assert "| TASK-1 | Old format | BACKLOG |  | 1 | proposal.md |  | 2026-09-22 |  | preserved |" in text


def test_legacy_alias_cannot_collide_with_current_id(repo):
    reg = registry(repo)
    reg.allocate("TASK", "One", anchor="proposal.md")
    with pytest.raises(LedgerError) as error:
        reg.allocate("ISSUE", "Alias collision", anchor="proposal.md", legacy="TASK-1")
    assert error.value.issue.code == "ERR_LEGACY_COLLISION"

    reg.allocate("TASK", "Reserved future alias", anchor="proposal.md", legacy="TASK-3")
    with pytest.raises(LedgerError) as error:
        reg.allocate("TASK", "Future current ID", anchor="proposal.md")
    assert error.value.issue.code == "ERR_LEGACY_COLLISION"


def test_worktree_content_is_distinct_from_index(repo, capsys):
    (repo / "proposal.md").write_text("TASK-90\n", encoding="utf-8")
    subprocess.run(["git", "add", "proposal.md"], check=True, capture_output=True)
    (repo / "proposal.md").write_text("clean worktree\n", encoding="utf-8")
    capsys.readouterr()
    assert main(["check", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["scope"]["view"] == "worktree"
    assert main(["check", "--staged", "--json"]) == 2


def test_custom_type_and_optional_anchor(repo):
    (repo / "ledger.toml").write_text(
        '[types.EXPERIMENT]\nallowed_statuses = ["PROPOSED"]\nrequire_anchor = false\n',
        encoding="utf-8")
    row = registry(repo).allocate("EXPERIMENT", "Custom")
    assert row.id == "EXPERIMENT-1"
    assert main(["check"]) == 0

@pytest.mark.parametrize("relation", ["parent", "supersedes"])
def test_relation_cycle_and_self_reference(repo, relation, capsys):
    reg = registry(repo)
    reg.allocate("TASK", "One", anchor="proposal.md")
    reg.allocate("TASK", "Two", anchor="proposal.md")
    setattr(reg.rows[0], relation, "TASK-2")
    setattr(reg.rows[1], relation, "TASK-1")
    reg.save()
    capsys.readouterr()
    assert main(["check", "--json"]) == 1
    assert "ERR_RELATION_CYCLE" in capsys.readouterr().out
    setattr(reg.rows[0], relation, "TASK-1")
    reg.save()
    assert main(["check", "--json"]) == 1
    assert "ERR_SELF_REFERENCE" in capsys.readouterr().out

def test_unknown_relation_rejected(repo):
    with pytest.raises(LedgerError) as error:
        registry(repo).allocate("TASK", "Bad", parent="TASK-99", anchor="proposal.md")
    assert error.value.issue.code == "ERR_RELATION_NOT_FOUND"

def test_scan_scope_aggregation_and_readonly(repo, capsys):
    reg = registry(repo)
    reg.allocate("TASK", "One", anchor="proposal.md")
    (repo / "new.md").write_text("TASK-999\n" * 25, encoding="utf-8")
    (repo / ".gitignore").write_text("ignored.md\n", encoding="utf-8")
    (repo / "ignored.md").write_text("TASK-888", encoding="utf-8")
    before = reg.path.read_bytes()
    capsys.readouterr()
    assert main(["check", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["issues"][0]["count"] == 25
    assert len(report["issues"][0]["locations"]) == 10
    assert "new.md" in report["scope"]["untracked"]
    assert "ignored.md" in report["scope"]["git_ignored"]
    assert reg.path.read_bytes() == before

def test_utf8_and_deleted_tracked_file_fail(repo, capsys):
    (repo / "proposal.md").write_bytes(b"\xff")
    capsys.readouterr()
    assert main(["check", "--json"]) == 3
    assert not json.loads(capsys.readouterr().out)["complete"]
    (repo / "proposal.md").unlink()
    assert main(["check", "--json"]) == 3

@pytest.mark.parametrize("flags", [["--staged"], ["--commit", "HEAD"], ["--incremental"]])
def test_unsupported_views_explicit(repo, flags, capsys):
    capsys.readouterr()
    assert main(["check", *flags, "--json"]) == 2
    assert "ERR_UNSUPPORTED_VIEW" in capsys.readouterr().out

@pytest.mark.parametrize("text", ['[ledger]\nallow_gaps = "false"', '[ledger]\nregistry_path = "../x"',
                                 '[types.TASK]\nallowed_statuses = []', '[ledger]\ntransitions = {}',
                                 '[ledger]\nschema_version = "9.0"', 'invalid toml'])
def test_config_fail_closed(repo, text, capsys):
    (repo / "ledger.toml").write_text(text, encoding="utf-8")
    capsys.readouterr()
    assert main(["check", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["issues"][0]["category"] == "configuration"

def test_init_never_overwrites(repo):
    before = (repo / "ledger.toml").read_bytes()
    assert main(["init"]) == 1
    assert (repo / "ledger.toml").read_bytes() == before

def test_linked_worktree_allocation_rejected(repo):
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-m", "fixture"], check=True, capture_output=True)
    linked = repo.parent / "linked"
    subprocess.run(["git", "worktree", "add", "--detach", str(linked)], check=True, capture_output=True)
    assert main(["init", "--root", str(linked)]) == 0
    with pytest.raises(LedgerError) as error:
        registry(linked).allocate("TASK", "No mint here", anchor="proposal.md")
    assert error.value.issue.code == "ERR_ALLOCATION_WORKTREE"

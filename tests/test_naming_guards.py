"""Full-name guard, letter-label guard and the ratchet baseline for historical text.

RULE: user-facing prose never shows a bare TYPE-N; ordinals carry digits only.
The fixtures below contain violations on purpose; each check must first go red
on them (red-before-green) and only then pass on the corrected spellings.
"""
from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

import pytest

from repo_ledger.cli import main


GIT_ID = ["-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid"]

NAMES = {
    "TASK-1": "预训练 ×2",
    "TASK-2": "图像层互斥断言",
    "ISSUE-1": "Deploy | rollback",
    "DATASET-12": "字体池清单 v2.2",
}
TYPES = ["TASK", "ISSUE", "DATASET"]


@pytest.fixture
def naming():
    # Imported inside the tests so a missing module fails each test on its own.
    return importlib.import_module("repo_ledger.naming")


def bare(naming, text, prefixes=None):
    hits = naming.find_missing_full_names(text.splitlines(), NAMES, TYPES, prefixes or {})
    return [(hit.line, hit.column, hit.token) for hit in hits]


def labels(naming, text):
    return [(hit.line, hit.token, hit.kind) for hit in naming.find_letter_labels(text.splitlines())]


# --------------------------------------------------------------------------- full names

@pytest.mark.parametrize("text", [
    "现在：TASK-1 预训练 ×2（IN_PROGRESS）",
    "TASK-1预训练 ×2 已落地",
    "**TASK-1** 预训练 ×2",
    "TASK-1 **预训练 ×2**",
    "TASK-1\u3000预训练 ×2",
    "预训练 ×2（TASK-1）",
    "**预训练 ×2**（TASK-1）",
    "预训练 ×2 (TASK-1, DONE)",
    "| TASK-1 | 预训练 ×2 | DONE |",
    "| 预训练 ×2 | TASK-1 |",
    "| ISSUE-1 | Deploy \\| rollback |",
    "TASK-1 预训练 ×2 与 TASK-2 图像层互斥断言",
    "DATASET-12 字体池清单 v2.2.",
    "Run `repo-ledger lookup TASK-1` first.",
    "```\nTASK-1\n```",
    "```legacy\nTASK-2\n```",
    "~~~text\nTASK-2 only\n~~~",
    "TASK-9 is not registered, so the reference check owns it",
    "TASK-014 has a leading zero and is not registered",
    "run id TASK-1-review-20260925 is a machine string",
    "XTASK-1 is glued to a letter",
])
def test_full_name_forms_that_pass(naming, text):
    assert bare(naming, text) == []


def test_bare_id_is_reported_with_its_column(naming):
    assert bare(naming, "现在：TASK-1 已完成") == [(1, 4, "TASK-1")]


@pytest.mark.parametrize("text", [
    "TASK-1  预训练 ×2",          # two spaces: at most one is allowed
    "TASK-1\t预训练 ×2",          # a tab is not a space
    "TASK-1 预训练",              # truncated name
    "TASK-1 预训练×2",            # altered name
    "见 (TASK-1)",                # parenthesised ID not preceded by the name
    "DATASET-12 字体池清单 v2.23",  # the name must end on a boundary
    "TASK-1：预训练 ×2",           # separators other than one space are not adjacency
])
def test_near_misses_are_reported(naming, text):
    hits = bare(naming, text)
    assert len(hits) == 1 and hits[0][2] in {"TASK-1", "DATASET-12"}


def test_every_mention_needs_the_name_not_only_the_first(naming):
    text = "TASK-1 预训练 ×2 已开跑；之后 TASK-1 继续"
    assert bare(naming, text) == [(1, text.rindex("TASK-1") + 1, "TASK-1")]


def test_a_name_broken_across_lines_is_not_adjacent(naming):
    assert bare(naming, "TASK-1 预训练\n×2 已开跑") == [(1, 1, "TASK-1")]


def test_slash_joined_ids_are_both_bare(naming):
    assert [hit[2] for hit in bare(naming, "见 TASK-1/TASK-2")] == ["TASK-1", "TASK-2"]


def test_table_cells_must_be_adjacent_id_and_name(naming):
    hits = bare(naming, "| TASK-1 | DONE | TASK-2 |")
    assert [hit[2] for hit in hits] == ["TASK-1", "TASK-2"]


# Review of the naming guards (2026-09-26), defect 6: "_" and "-" counted as word
# characters, so underscore emphasis and hyphenated words (TASK-1-clean) hid a bare ID.
@pytest.mark.parametrize("text", [
    "__TASK-1__ 已开跑",
    "_TASK-1_ 已开跑",
    "final TASK-1-clean selection",
    "post-TASK-1 状态",
    "见 TASK-1_pool 目录",
    "TASK-1-review-2026092 缺一位日期",
    "TASK-1-Review-20260925 技能名大写",
    "TASK-1-review-20261399 日期不成立",
    "TASK-1-20260925 没有技能名",
    "TASK-1-review-20260925_x 后面还连着",
])
def test_id_boundary_underscore_and_hyphen_are_checked(naming, text):
    assert [hit[2] for hit in bare(naming, text)] == ["TASK-1"]


@pytest.mark.parametrize("text", [
    "__TASK-1__ 预训练 ×2",
    "_TASK-1_ 预训练 ×2",
    "_预训练 ×2_（TASK-1）",
    "run id TASK-1-review-20260925 is a machine string",
    "aris-work/TASK-1-experiment-audit-20260925/ 下的产出",
    "见 TASK-1-review-v2-20260925.json",
])
def test_id_boundary_exact_run_ids_and_emphasis_pass(naming, text):
    assert bare(naming, text) == []


def test_display_prefix_follows_the_same_rule(naming):
    prefixes = {"任务": "TASK"}
    assert bare(naming, "见任务-1 预训练 ×2", prefixes) == []
    assert bare(naming, "任务-1 进行中", prefixes) == [(1, 1, "任务-1")]
    # Without a configured display prefix the display spelling is not a mention.
    assert bare(naming, "任务-1 进行中") == []


# --------------------------------------------------------------------------- letter labels

@pytest.mark.parametrize("text,expected", [
    ("按 §2a 不跑 fast", ("§2a", "section")),
    ("文末 §0c 是更正", ("§0c", "section")),
    ("见 §1a.3", ("§1a.3", "section")),
    ("见 §3A 的登记集", ("§3A", "section")),
    ("附录 B §B8 的顺序", ("§B8", "section")),
    ("章节指针 §B3.3 要改", ("§B3.3", "section")),
    ("佐证写入附表 D §D.3。", ("§D.3", "section")),
    ("规格见 NEXT_PROMPT §C 七项", ("§C", "section")),
    ("The commit carries a section 2a receipt", ("section 2a", "section")),
    ("Phase 2.6 步骤 2a：dev 掩码", ("步骤 2a", "step")),
    ("regenerated by the driver (Phase 2.6 step 3c).", ("step 3c", "step")),
    ("- **3g 证伪条件一（PRESENT 未过**", ("3g", "list")),
    ("3c 附表 A（statsmodels）", ("3c", "list")),
    ("见第 2a 节", ("第 2a 节", "section")),
    ("## 0a. 结论表", ("0a", "heading")),
    ("#### 2a addendum (2026-09-23)", ("2a", "heading")),
    ("## A. 时序：是硬约束", ("A.", "heading")),
    ("## (i) Per-cell mean delta", ("(i)", "heading")),
    ("## Q6. Headline results", ("Q6.", "heading")),
    ("(a) **登记**：一行", ("(a)", "list")),
    ("- **(b) 编辑性同步**：仅限", ("(b)", "list")),
    ("a. first option", ("a.", "list")),
    ("b) second option", ("b)", "list")),
    ("> (c) quoted option", ("(c)", "list")),
    ("   - (ii) nested option", ("(ii)", "list")),
    ("2a. numbered with a letter", ("2a.", "list")),
    ("| 2a | MX-Font | ICCV 2021 |", ("2a", "table")),
    ("| (a) | 维持链 |", ("(a)", "table")),
    ("选 (ii) 的版本策略", ("(ii)", "inline")),
    ("处置 (b) 冻结提交内改措辞", ("(b)", "inline")),
    ("**9/38**。**(a) 下 qiji", ("(a)", "inline")),
])
def test_letter_labels_are_reported(naming, text, expected):
    assert labels(naming, text) == [(1, *expected)]


@pytest.mark.parametrize("text", [
    "见 §2.1 与 §12",
    "## 2.1 测试分档",
    "## A100 显卡报价",
    "## 1st round",
    "e.g. this is prose",
    "i.e. that too",
    "1. a plain numbered item",
    "| A | 可定位 |",
    "| 2.1 | nested number |",
    "f(a) = 1 and E*(c) is a working point",
    "(n−1)ρ is the inflation",
    "- 4h 后重试",
    "2x2 设计与 3D 渲染",
    "Phase 2.6 dev 调参 step 12",
    "ANALYSIS-8 附表 A 功效仿真 与 缺陷 A、B",
    "Quote `§2a` and `(b)` inside code",
    "```\n## 0a. inside a fence\n(a) also inside\n```",
    "```legacy\n§B3.3 teaching example\n```",
])
def test_letter_label_non_violations(naming, text):
    assert labels(naming, text) == []


def test_one_span_is_reported_once(naming):
    assert labels(naming, "## §0c 2026-09-25 更正") == [(1, "§0c", "section")]


def test_several_labels_on_one_line(naming):
    found = labels(naming, "(a) 保留灵敏度；(b) 干净但放弃")
    assert found == [(1, "(a)", "list"), (1, "(b)", "inline")]


def test_unclosed_fence_masks_to_the_end(naming):
    assert labels(naming, "intro\n```\n§2a\n(b) x") == []


# Review of the naming guards (2026-09-26), defect 2: uppercase suffixes were never
# reported (a project's live file wrote "Phase 4A").
@pytest.mark.parametrize("text,expected", [
    ("The plan's Phase 4A line", ("Phase 4A", "step")),
    ("## Phase 4A: 第二骨干", ("Phase 4A", "step")),
    ("step 2A of the driver", ("step 2A", "step")),
    ("按 Phase 4B 的 NEGATIVE 路线", ("Phase 4B", "step")),
    ("## 2A 标题", ("2A", "heading")),
    ("| 2A | 第二骨干 |", ("2A", "table")),
    ("- 2B 候选", ("2B", "list")),
])
def test_uppercase_suffix_labels_are_reported(naming, text, expected):
    assert labels(naming, text) == [(1, *expected)]


@pytest.mark.parametrize("text", [
    "## 3D 渲染管线",                       # dimensions are not labels
    "| 3D | 支持 |",
    "- 2D 与 3D 对照",
    "## 1st round",
    "RTX 4090、A100、H100、T4 与 L4 报价",   # product names
    "Qwen2.5-7B 与 Llama-3-8B 不在本项目",
    "U+767D 与 U+0751C 是码位",
    "Option 3R 候选提供器",                  # an option name, like 附录 B
])
def test_uppercase_suffix_non_violations(naming, text):
    assert labels(naming, text) == []


# Defect 5: a parenthesised letter glued to a number was never reported
# (a project's register wrote "26.5(a)").
@pytest.mark.parametrize("text,expected", [
    ("按 ROLE_POLICY §2(a) 执行", ("§2(a)", "section")),
    ("依据登记 26.5(a) 与 §7 第 8 项", ("26.5(a)", "inline")),
    ("见 §3.1(b)", ("§3.1(b)", "section")),
    ("对照 §9(c)(e) 两条", ("§9(c)(e)", "section")),
    ("## 2(a) 标题", ("2(a)", "heading")),
    ("- 2(b) 选项", ("2(b)", "list")),
    ("| 2(a) | 维持链 |", ("2(a)", "table")),
    ("见第 2(a) 节", ("第 2(a) 节", "section")),
    ("已处理 ISSUE-3(a)", ("3(a)", "inline")),
    ("Phase 2.6 step 1(b)", ("step 1(b)", "step")),
    ("意见书 2.1(ii) 的措辞", ("2.1(ii)", "inline")),
])
def test_parenthesised_letter_after_number_is_reported(naming, text, expected):
    assert labels(naming, text) == [(1, *expected)]


@pytest.mark.parametrize("text", [
    "E_2(c) 与 f_1(a) 是函数值",
    "x2(b) 与 v2.1(a) 不是序号",
    "f(2)(a) 是柯里化",
    "2(n+1) 与 3(x+y) 是乘积",
])
def test_parenthesised_letter_after_number_non_violations(naming, text):
    assert labels(naming, text) == []


# Found by a project's cleanup pass after the review: abbreviated section pointers
# ("sec 0c", "sec 1a.1") were never reported.
@pytest.mark.parametrize("text,expected", [
    ("按任务书 sec 0c 的更正", ("sec 0c", "section")),
    ("see sec 1a.1 and sec 1a.2", ("sec 1a.1", "section")),
    ("Sec. 2A 的登记表", ("Sec. 2A", "section")),
    ("Sec 3b covers it", ("Sec 3b", "section")),
    ("sec.3b 规则", ("sec.3b", "section")),
    ("详见 sec0c", ("sec0c", "section")),
    ("sec 2(a) 与", ("sec 2(a)", "section")),
    ("the section 1a.3 receipt", ("section 1a.3", "section")),
    ("sections 2b 与 2c", ("sections 2b", "section")),
])
def test_sec_abbreviation_pointers_are_reported(naming, text, expected):
    assert labels(naming, text)[0] == (1, *expected)


@pytest.mark.parametrize("text", [
    "timeout 30 sec，每 5 secs 重试",
    "见 sec 3.2 与 section 12",
    "second 2a 不是章节",
    "insecure 2a 也不是",
])
def test_sec_abbreviation_non_violations(naming, text):
    assert labels(naming, text) == []


def test_line_digest_is_stable_and_trailing_space_insensitive(naming):
    digest = naming.line_digest("见 §2a")
    assert len(digest) == 16 and all(ch in "0123456789abcdef" for ch in digest)
    assert naming.line_digest("见 §2a  \r") == digest
    assert naming.line_digest("见 §2b") != digest


# --------------------------------------------------------------------------- CLI, scope and baseline

BASE = '[ledger]\nschema_version = "1.0"\nallow_gaps = true\n'
NAMING_CONFIG = '''
[full_name_guard]
enabled = true
scope_globs = ["STATUS.md", "log/*.md", "archive/**"]
display_prefixes = { "任务" = "TASK" }

[letter_label_guard]
enabled = true
scope_globs = ["*.md", "**/*.md"]
exclude_globs = ["vendor/**"]

[naming_baseline]
path = "NAMING_BASELINE.tsv"
history_globs = ["log/*.md", "archive/**"]
live_globs = ["log/current.md"]
'''


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *GIT_ID, *args], check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def configure(root, extra=NAMING_CONFIG):
    write(root, "ledger.toml", BASE + extra)


def run_json(capsys, argv):
    capsys.readouterr()
    rc = main(argv)
    return rc, json.loads(capsys.readouterr().out)


def issue_codes(report):
    return sorted({issue["code"] for issue in report["issues"]})


def emit(capsys):
    capsys.readouterr()
    assert main(["check-naming", "--emit-baseline"]) == 0
    return capsys.readouterr().out


@pytest.fixture
def repo(tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    git(tmp_path, "config", "core.autocrlf", "false")
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    write(tmp_path, "proposal.md", "# Proposal\n")
    git(tmp_path, "add", "proposal.md")
    for type_name, name in (("TASK", "预训练 ×2"), ("TASK", "图像层互斥断言"),
                            ("ISSUE", "Deploy | rollback")):
        assert main(["allocate", type_name, name, "--anchor", "proposal.md"]) == 0
    capsys.readouterr()
    return tmp_path


def test_guards_are_off_by_default(repo, capsys):
    # A project without any naming table sees no change in check's report (the convention the
    # [index] table follows); configured but switched-off guards report "disabled" (see
    # test_emit_baseline_evaluates_guards_that_are_still_switched_off).
    write(repo, "STATUS.md", "现在：TASK-1 已完成，见 §2a\n")
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 0
    assert "naming_guard" not in report["scope"]


def test_live_file_violations_are_red(repo, capsys):
    configure(repo)
    write(repo, "STATUS.md", "现在：TASK-1 已完成，见 §2a\n")
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 1
    locations = {(issue["code"], loc) for issue in report["issues"] for loc in issue["locations"]}
    assert ("ERR_MISSING_FULL_NAME", "STATUS.md:1:4") in locations
    assert ("ERR_LETTER_LABEL", "STATUS.md:1:17") in locations
    missing = next(issue for issue in report["issues"] if issue["code"] == "ERR_MISSING_FULL_NAME")
    assert missing["entity"] == "TASK-1"
    assert "TASK-1 预训练 ×2" in missing["reason"]


def test_corrected_live_file_is_green(repo, capsys):
    configure(repo)
    write(repo, "STATUS.md", "现在：TASK-1 预训练 ×2 已完成，见 `ROLE.md` §2.1 测试分档\n")
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 0, report["issues"]
    audit = report["scope"]["naming_guard"]
    assert "STATUS.md" in audit["full_name_guard"]["scanned"]
    assert "STATUS.md" in audit["letter_label_guard"]["scanned"]


def test_letter_guard_scope_and_exclusions(repo, capsys):
    configure(repo)
    write(repo, "vendor/README.md", "## 2a. vendored text\n")
    write(repo, "notes/plan.md", "## 2a. our text\n")
    rc, report = run_json(capsys, ["check-naming", "--json"])
    assert rc == 1
    locations = [loc for issue in report["issues"] for loc in issue["locations"]]
    assert locations == ["notes/plan.md:1:4"]


def test_baseline_suppresses_historical_text_and_stays_visible(repo, capsys):
    configure(repo)
    write(repo, "log/2026.md", "- 旧行：TASK-1 已完成\n- 旧行：见 §0c\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 0, report["issues"]
    baseline = report["scope"]["naming_guard"]["baseline"]
    assert baseline["suppressed"] == {"full_name": 1, "letter_label": 1}
    assert baseline["rows"] == 2


def test_emitted_baseline_skips_live_files_and_is_sorted(repo, naming, capsys):
    configure(repo)
    write(repo, "log/2026.md", "见 §0c\nTASK-2 旧写法\n")
    write(repo, "log/current.md", "TASK-1 现在\n")
    text = emit(capsys)
    lines = text.splitlines()
    assert lines[0] == f"# repo-ledger naming baseline; rules={naming.NAMING_RULES_VERSION}"
    assert "check\tfile\tline_sha256\tcount" in lines
    rows = [line.split("\t") for line in lines if not line.startswith("#") and not line.startswith("check\t")]
    assert rows == sorted(rows)
    assert {row[1] for row in rows} == {"log/2026.md"}
    assert {(row[0], row[2]) for row in rows} == {
        ("letter_label", naming.line_digest("见 §0c")),
        ("full_name", naming.line_digest("TASK-2 旧写法")),
    }


def test_live_file_in_history_directory_is_never_baselined(repo, capsys):
    configure(repo)
    write(repo, "log/current.md", "TASK-1 现在\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 1
    assert issue_codes(report) == ["ERR_MISSING_FULL_NAME"]


def test_new_line_in_a_historical_file_is_red(repo, capsys):
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 旧写法\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    write(repo, "log/2026.md", "TASK-1 旧写法\nTASK-2 新写的一行\n")
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 1
    locations = [loc for issue in report["issues"] for loc in issue["locations"]]
    assert locations == ["log/2026.md:2:1"]


def test_fixed_line_leaves_a_stale_row_that_is_red(repo, capsys):
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 旧写法\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    write(repo, "log/2026.md", "TASK-1 预训练 ×2 旧写法\n")
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 1
    assert issue_codes(report) == ["ERR_NAMING_BASELINE_STALE"]
    assert report["issues"][0]["locations"] == ["NAMING_BASELINE.tsv:3:1"]


def test_row_for_a_live_file_is_a_scope_error(repo, naming, capsys):
    configure(repo)
    write(repo, "STATUS.md", "TASK-1 现在\n")
    rules = naming.NAMING_RULES_VERSION
    write(repo, "NAMING_BASELINE.tsv",
          f"# repo-ledger naming baseline; rules={rules}\ncheck\tfile\tline_sha256\tcount\n"
          f"full_name\tSTATUS.md\t{naming.line_digest('TASK-1 现在')}\t1\n")
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 1
    assert issue_codes(report) == ["ERR_MISSING_FULL_NAME", "ERR_NAMING_BASELINE_SCOPE"]


def test_baseline_cannot_grow_after_it_is_committed(repo, capsys):
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 旧写法\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "baseline")
    write(repo, "log/2026.md", "TASK-1 旧写法\nTASK-2 新写的一行\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))       # the forbidden move
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 1
    assert issue_codes(report) == ["ERR_NAMING_BASELINE_GROWTH"]
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "grow the baseline")
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 1
    assert issue_codes(report) == ["ERR_NAMING_BASELINE_GROWTH"]
    assert report["scope"]["naming_guard"]["baseline"]["ratchet"]["status"] == "verified"


def test_deleting_and_recreating_the_baseline_does_not_reset_the_ratchet(repo, capsys):
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 旧写法\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "baseline")
    git(repo, "rm", "-q", "NAMING_BASELINE.tsv")
    git(repo, "commit", "-m", "drop baseline")
    write(repo, "log/2026.md", "TASK-1 旧写法\nTASK-2 新写的一行\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "recreate a larger baseline")
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 1
    assert issue_codes(report) == ["ERR_NAMING_BASELINE_GROWTH"]


def test_moving_a_historical_file_keeps_its_rows(repo, capsys):
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 旧写法\n见 §0c\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "baseline")
    (repo / "archive").mkdir()
    git(repo, "mv", "log/2026.md", "archive/2026.md")
    baseline = (repo / "NAMING_BASELINE.tsv").read_text(encoding="utf-8")
    write(repo, "NAMING_BASELINE.tsv", baseline.replace("log/2026.md", "archive/2026.md"))
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 0, report["issues"]


# Review of the naming guards (2026-09-26), defect 3: a registry rename turned compliant
# historical lines red, and re-emitting the baseline to absorb them was growth.
def rename(repo, old, new):
    registry = repo / ".ledger" / "ENTITY_REGISTRY.md"
    text = registry.read_text(encoding="utf-8")
    assert f"| {old} |" in text
    registry.write_text(text.replace(f"| {old} |", f"| {new} |"), encoding="utf-8", newline="\n")


def test_rename_keeps_compliant_historical_lines_green(repo, capsys):
    configure(repo)
    write(repo, "log/2026.md", "- 2026-09-26 TASK-1 预训练 ×2 已开跑\n- 预训练 ×2（TASK-1）\n"
                               "| TASK-1 | 预训练 ×2 |\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "baseline")
    rename(repo, "预训练 ×2", "跨字体预训练 ×2")
    git(repo, "commit", "-qam", "rename TASK-1")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))   # re-emitting must not grow
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 0, report["issues"]
    audit = report["scope"]["naming_guard"]
    assert audit["baseline"]["rows"] == 0
    assert audit["full_name_guard"]["former_names"]["entities"] == 1


def test_rename_in_the_worktree_only_keeps_the_committed_name(repo, capsys):
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 预训练 ×2 已开跑\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "registry and log")
    rename(repo, "预训练 ×2", "跨字体预训练 ×2")        # not committed yet
    rc, report = run_json(capsys, ["check-naming", "--json"])
    assert rc == 0, report["issues"]


def test_rename_requires_the_current_name_in_live_files(repo, capsys):
    configure(repo)
    write(repo, "STATUS.md", "现在：TASK-1 预训练 ×2 已开跑\n")
    write(repo, "log/current.md", "TASK-1 预训练 ×2\n")   # live file inside a history directory
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "status")
    rename(repo, "预训练 ×2", "跨字体预训练 ×2")
    git(repo, "commit", "-qam", "rename TASK-1")
    rc, report = run_json(capsys, ["check-naming", "--json"])
    assert rc == 1
    locations = sorted(loc for issue in report["issues"] for loc in issue["locations"])
    assert locations == ["STATUS.md:1:4", "log/current.md:1:1"]
    assert "TASK-1 跨字体预训练 ×2" in report["issues"][0]["reason"]


def test_rename_never_accepts_a_name_that_was_not_registered(repo, capsys):
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 预训练 ×2\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "baseline")
    rename(repo, "预训练 ×2", "跨字体预训练 ×2")
    git(repo, "commit", "-qam", "rename TASK-1")
    write(repo, "log/2026.md", "TASK-1 预训练 ×2\nTASK-1 预训练 新写的简称\n")
    rc, report = run_json(capsys, ["check-naming", "--json"])
    assert rc == 1
    assert [loc for issue in report["issues"] for loc in issue["locations"]] == ["log/2026.md:2:1"]


def test_rename_that_fixes_a_baselined_line_leaves_a_stale_row_to_delete(repo, capsys):
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 跨字体预训练 ×2 写在改名之前\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "baseline with one row")
    rename(repo, "预训练 ×2", "跨字体预训练 ×2")
    git(repo, "commit", "-qam", "rename TASK-1")
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 1 and issue_codes(report) == ["ERR_NAMING_BASELINE_STALE"]
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))   # the row goes: a shrink
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 0, report["issues"]


def test_former_names_are_opt_in_for_the_matcher(naming):
    assert bare(naming, "TASK-1 旧名") == [(1, 1, "TASK-1")]
    hits = naming.find_missing_full_names(["TASK-1 旧名", "旧名（TASK-1）"], NAMES, TYPES, {},
                                          former_names={"TASK-1": ["旧名"]})
    assert hits == []


# Review of the naming guards (2026-09-26), defect 4: in a shallow clone the ratchet
# compared with the earliest fetched version and reported "verified" for a grown baseline.
def grown_baseline(repo, capsys):
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 旧写法\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "baseline")
    write(repo, "log/2026.md", "TASK-1 旧写法\nTASK-2 新写的一行\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))   # the forbidden growth
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "grow the baseline")


def shallow_clone(repo, target):
    subprocess.run(["git", "clone", "-q", "--depth", "1", repo.as_uri(), str(target)],
                   check=True, capture_output=True)
    git(target, "config", "core.autocrlf", "false")
    assert git(target, "rev-parse", "--is-shallow-repository").strip() == "true"


def test_shallow_clone_never_claims_a_verified_ratchet(repo, tmp_path, capsys, monkeypatch):
    grown_baseline(repo, capsys)
    clone = tmp_path / "shallow"
    shallow_clone(repo, clone)
    monkeypatch.chdir(clone)
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 3 and report["complete"] is False
    assert report["scope"]["naming_guard"]["baseline"]["ratchet"]["status"] == "unverified: shallow clone"
    shallow = [issue for issue in report["issues"] if issue["code"] == "ERR_NAMING_HISTORY_SHALLOW"]
    assert len(shallow) == 1 and "git fetch --unshallow" in shallow[0]["suggestion"]
    # The instruction works: with the full history the growth is visible and verified.
    git(clone, "fetch", "-q", "--unshallow")
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 1 and issue_codes(report) == ["ERR_NAMING_BASELINE_GROWTH"]
    assert report["scope"]["naming_guard"]["baseline"]["ratchet"]["status"] == "verified"


def test_shallow_clone_refuses_to_emit_a_baseline(repo, tmp_path, capsys, monkeypatch):
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 预训练 ×2\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "registry and log")
    clone = tmp_path / "shallow"
    shallow_clone(repo, clone)
    monkeypatch.chdir(clone)
    capsys.readouterr()
    assert main(["check-naming", "--emit-baseline"]) == 3
    assert "git fetch --unshallow" in capsys.readouterr().err
    git(clone, "fetch", "-q", "--unshallow")
    assert main(["check-naming", "--emit-baseline"]) == 0


# The rework changed which lines count (defects 2, 3, 5, 6 and "sec"), after a rules=1
# baseline had been committed on a project branch: rules version 2 skips such a baseline
# instead of treating it as the ratchet root.
def test_rules_version_2_skips_a_committed_version_1_baseline(repo, naming, capsys):
    assert naming.NAMING_RULES_VERSION == 2
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 旧写法\n")
    write(repo, "NAMING_BASELINE.tsv", "# repo-ledger naming baseline; rules=1\n"
                                       "check\tfile\tline_sha256\tcount\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "an empty baseline under the old rules")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the baseline under the current rules")
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 0, report["issues"]
    ratchet = report["scope"]["naming_guard"]["baseline"]["ratchet"]
    assert ratchet["status"] == "verified"
    assert ratchet["root_commit"] == git(repo, "rev-parse", "HEAD").strip()
    assert [version["commit"] for version in ratchet["skipped_versions"]] == [
        git(repo, "rev-parse", "HEAD~1").strip()[:8]]


def test_uncommitted_baseline_is_reported_as_unverified(repo, capsys):
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 旧写法\n")
    write(repo, "NAMING_BASELINE.tsv", emit(capsys))
    rc, report = run_json(capsys, ["check-naming", "--json"])
    assert rc == 0
    assert report["scope"]["naming_guard"]["baseline"]["ratchet"]["status"] == "not committed"


@pytest.mark.parametrize("mutate", [
    lambda text: text.replace("rules=", "rules=9"),
    lambda text: "# something else\n" + text.split("\n", 1)[1],
    lambda text: text.replace("check\tfile\tline_sha256\tcount", "check\tfile\tcount"),
    lambda text: text + text.splitlines()[-1] + "\n",
    lambda text: text.replace("\t1\n", "\t0\n"),
    lambda text: text.replace("\t1\n", "\tone\n"),
    lambda text: text.rsplit("\t", 2)[0] + "\tXYZ\t1\n",
    lambda text: text.replace("full_name\t", "spelling\t"),
    lambda text: text.replace("log/2026.md", "../2026.md"),
])
def test_malformed_baseline_fails_closed(repo, capsys, mutate):
    configure(repo)
    write(repo, "log/2026.md", "TASK-1 旧写法\n")
    write(repo, "NAMING_BASELINE.tsv", mutate(emit(capsys)))
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 2
    assert report["issues"][0]["code"] == "ERR_NAMING_BASELINE"


@pytest.mark.parametrize("extra", [
    '[full_name_guard]\nenabled = true\nsurprise = 1\n',
    '[full_name_guard]\nenabled = "yes"\n',
    '[full_name_guard]\nscope_globs = ["../outside.md"]\n',
    '[full_name_guard]\ndisplay_prefixes = { "任务" = "WIDGET" }\n',
    '[full_name_guard]\ndisplay_prefixes = { "TASK" = "TASK" }\n',
    '[letter_label_guard]\nexclude_globs = "vendor/**"\n',
    '[naming_baseline]\npath = "/abs/baseline.tsv"\n',
    '[naming_baseline]\nhistory_globs = ["C:/x"]\n',
])
def test_invalid_naming_configuration_is_rejected(repo, capsys, extra):
    configure(repo, extra)
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 2
    assert report["issues"][0]["code"] == "ERR_CONFIG"


def test_check_naming_runs_only_the_naming_guards(repo, capsys):
    configure(repo)
    write(repo, "STATUS.md", "TASK-1 现在\n")
    write(repo, "other.md", "Refers to TASK-99, unregistered\n")
    rc, report = run_json(capsys, ["check-naming", "--json"])
    assert rc == 1
    assert issue_codes(report) == ["ERR_MISSING_FULL_NAME"]
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 1
    assert issue_codes(report) == ["ERR_MISSING_FULL_NAME", "ERR_UNREGISTERED_ENTITY"]


def test_table_row_with_a_pipe_in_the_name(repo, capsys):
    configure(repo)
    write(repo, "STATUS.md", "| ISSUE-1 | Deploy \\| rollback | OPEN |\n")
    rc, report = run_json(capsys, ["check-naming", "--json"])
    assert rc == 0, report["issues"]


def test_emit_baseline_evaluates_guards_that_are_still_switched_off(repo, capsys):
    # A project prepares its baseline before it switches the guards on.
    configure(repo, NAMING_CONFIG.replace("enabled = true", "enabled = false"))
    write(repo, "log/2026.md", "TASK-1 旧写法\n见 §0c\n")
    rows = [line.split("\t")[0] for line in emit(capsys).splitlines()[2:]]
    assert sorted(rows) == ["full_name", "letter_label"]
    rc, report = run_json(capsys, ["check", "--json"])
    assert rc == 0 and report["scope"]["naming_guard"]["status"] == "disabled"

"""Naming guards for prose: full registered names and digit-only ordinals.

Both guards are opt-in through ledger.toml and line-oriented over Markdown text.
Fenced code blocks (``` or ~~~, including ```legacy teaching fences) and inline
code spans are masked before matching; the registry is parsed separately and is
never scanned.

Full-name guard (``[full_name_guard]``, user-facing files only).  Every
registered ``TYPE-N`` -- and every configured display spelling such as
``任务-N`` -- must be adjacent to its full registered name on the same line.
Adjacent means exactly one of:

  A. ID, then at most one space (U+0020, U+00A0 or U+3000), then the name:
     ``TASK-33 预训练 ×2``
  B. name, then at most one space, then an opening parenthesis ``(`` or
     ``（`` whose first content is the ID:  ``预训练 ×2（TASK-33）``
  C. table cells: the ID is a whole cell and a neighbouring cell (left or
     right) is exactly the name:  ``| TASK-33 | 预训练 ×2 |``

Emphasis markers (``**``, ``*``, ``__``, ``_``) may wrap the ID or the name.
A name ending in an ASCII letter or digit must not run on into another one
(``字体池清单 v2.2`` does not match ``v2.23``).  IDs that are not registered
(unknown, zero-padded) belong to the reference check and are skipped here.

What counts as a mention: an ID not glued to an ASCII letter or digit on either
side.  ``_``, ``-``, ``*`` and non-ASCII text are boundaries, so ``_TASK-33_``,
``__TASK-33__``, ``RULE-6-clean``, ``post-DATASET-4`` and ``见TASK-33`` are all
mentions.  The single exemption is an exact machine run id
``<TYPE-N>-<skill>-<YYYYMMDD>`` (``TASK-33-experiment-audit-20260925``): the skill
starts with a lowercase letter and holds lowercase letters, digits and single
hyphens, the date is eight digits shaped like a calendar date, and no letter,
digit, ``_`` or ``-`` follows.  Anything else glued to an ID is checked.

Renames.  In historical files (baseline ``history_globs`` minus ``live_globs``)
the adjacent name may also be one the entity carried in any committed version
of the registry file (``git log --follow`` of the registry path), so renaming an
entity never turns a line that was compliant when written red, and no baseline
row is needed for it.  This is deliberately looser than "the name in force when
the line was written" (no per-line blame); it admits only names that were once
the registered full name.  Live files, the rest of the scope and chat replies
need the current name.  A baselined line that a rename makes compliant leaves a
stale row: delete it (the baseline shrinks).

Letter-label guard (``[letter_label_guard]``).  Ordinals carry digits only; a
dotted number (``§2.1``) is the way to express levels.  Reported shapes:

  section  ``§2a`` ``§0c`` ``§1a.3`` ``§3A`` ``§B3.3`` ``§B8`` ``§D.3`` ``§A``,
           ``§2(a)`` ``§3.1(b)`` ``§9(c)(e)``, ``section 2a``, ``section 1a.3``,
           the abbreviations ``sec 0c`` ``sec.3b`` ``Sec. 2A`` ``sec0c``,
           ``第 2a 节``, ``第 2(a) 节``
  step     ``步骤 2a``, ``阶段 2a``, ``step 3c``, ``Phase 2a``, ``stage 1b``,
           ``Phase 4A``, ``step 1(b)`` (a number plus one letter a-h or A-H,
           or plus parenthesised letters)
  heading  ATX heading whose leading label has a letter: ``## 0a.``,
           ``#### 2a addendum``, ``## 2A 标题``, ``## 2(a)``, ``## A.``,
           ``## (i)``, ``## Q6.``
  list     line-start label after optional quote/list markers and emphasis:
           ``(a)`` ``a.`` ``b)`` ``(ii)`` ``2a.`` ``2(b)``, and ``3c`` or ``2B``
           followed by a space (letters a-g and A-G except D, so ``4h`` for
           hours and ``3D`` stay silent)
  table    first table cell that is a number plus one letter a-h or A-H except
           D (``| 2a |``, ``| 2A |``), a number plus parenthesised letters
           (``| 2(a) |``) or a parenthesised letter (``| (a) |``)
  inline   mid-line ``(a)``-``(h)``, ``(A)``-``(H)`` or roman ``(i)``-``(x)``
           that is not glued to a preceding letter, digit, ``)``, ``]`` or
           ``X*`` (so ``f(a)`` and ``E*(c)`` stay silent); and the same
           letters glued to a number (``26.5(a)``, ``ISSUE-3(a)``,
           ``2.1(ii)``) unless the number continues a word, an index or a
           version (``E_2(c)``, ``x2(b)``, ``v2.1(a)``, ``f(2)(a)``)

Uppercase suffixes: without a section or step word, ``D`` is not read as a label
(``2D``, ``3D`` are dimensions); after one (``Phase 4D``) it is.  Other uppercase
letters count, so a heading, list item or first table cell that starts with a size
such as ``7B`` is reported -- move the size later in the line.

Deliberately not reported: letter names such as ``附录 B``, ``附表 A``,
``缺陷 A、B`` or ``Option 3R`` (several are registered entity names), bare ``2a``
without a section marker, English ordinals (``1st``) and dimensions (``3D``).

Historical text is carried by a ratchet baseline (``[naming_baseline]``): rows
``check, file, line_sha256, count`` cover today's violations in files that match
``history_globs`` and not ``live_globs``.  A row suppresses that many hits on
lines with that exact text in that file.  Rows that match nothing are stale
(red); rows for live or non-historical files are scope errors (red); and the
multiset of ``(check, line_sha256)`` may never exceed the first committed
version of the baseline written under the current rules version (red), so the
baseline can shrink but never grow -- deleting and re-adding it does not reset
the ratchet, while moving a historical file keeps its rows.
"""
from collections import Counter
from dataclasses import dataclass
import fnmatch
import hashlib
import re
import subprocess

from .config import relative_path
from .errors import Issue, LedgerError
from .git import git, inventory, safe_file
from .registry import ID_RE, LAYOUTS, _split_row_cells

NAMING_RULES_VERSION = 1
BASELINE_HEADER = f"# repo-ledger naming baseline; rules={NAMING_RULES_VERSION}"
BASELINE_COLUMNS = "check\tfile\tline_sha256\tcount"
CHECKS = ("full_name", "letter_label")

EMPHASIS = ("", "**", "__", "*", "_")
SPACES = ("", " ", " ", "　")
OPEN_PARENS = ("(", "（")

_TAIL = r"(?=[\s*_]|$|[^\x00-\x7f])"
_LETTER_OR_ROMAN = r"(?:[A-Za-z]|[ivxlc]{2,5}|[IVXLC]{2,5})"
# One label letter after a number where no "section" or "step" word says it is a label:
# a-h, and A-H except D, because 2D and 3D are dimensions.
_SUFFIX = r"[a-hA-CE-H]"
# One or more parenthesised letters glued to a number: 2(a), 3.1(b), 9(c)(e), 2.1(ii).
_PAREN_LETTERS = r"(?:[(（]" + _LETTER_OR_ROMAN + r"[)）])+"

SECTION_RES = (
    re.compile(r"§[ \t]?(?:[A-Za-z]+\.?\d+(?:\.\d+)*[A-Za-z]*(?:\.\d+)*"
               r"|\d+(?:\.\d+)*(?:[A-Za-z]+(?:\.\d+)*|" + _PAREN_LETTERS + r"))(?![A-Za-z0-9])"),
    re.compile(r"§[ \t]?(?:[A-Z]|[IVX]{2,4})(?![A-Za-z0-9])"),
    # section 2a, sections 2b, sec 0c, Sec. 2A, sec.3b, sec0c, section 1a.3, sec 2(a)
    re.compile(r"(?<![A-Za-z])(?:[Ss]ections?|[Ss]ecs?\.?)[ \t]?\d+(?:\.\d+)*"
               r"(?:[A-Za-z](?:\.\d+)*|" + _PAREN_LETTERS + r")(?![A-Za-z0-9])"),
    re.compile(r"第[ \t]?\d+(?:\.\d+)*(?:[A-Za-z]+(?:\.\d+)*|" + _PAREN_LETTERS + r")[ \t]?[节章条款]"),
)
# After an explicit step word every letter a-h and A-H is a label (Phase 4A, step 2D).
STEP_RE = re.compile(r"(?<![A-Za-z])(?:[Ss]tep|[Pp]hase|[Ss]tage|步骤|阶段)[ \t]?\d+(?:\.\d+)*"
                     r"(?:[a-hA-H]|" + _PAREN_LETTERS + r")(?![A-Za-z0-9])")
HEADING_START = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(?:\*\*|__|\*|_)?")
HEADING_LABELS = (
    # 0a.  3A.  5a′.  1a.3)  -- a number with letters, closed by . or )
    re.compile(r"§?[ \t]?\d+(?:\.\d+)*[A-Za-z]+(?:\.\d+)*′?(?=[.)](?:[\s*_]|$|[^\x00-\x7f]))"),
    # 2(a)  3.1(b)  -- a number with parenthesised letters
    re.compile(r"§?[ \t]?\d+(?:\.\d+)*" + _PAREN_LETTERS + r"(?![A-Za-z0-9])"),
    # 2a addendum, 2A 标题, 0c 更正, 1a.3 xyz -- one letter (_SUFFIX), then a boundary
    re.compile(r"§?[ \t]?\d+(?:\.\d+)*" + _SUFFIX + r"(?:\.\d+)*′?" + _TAIL),
    # Q6.  D4.
    re.compile(r"[A-Za-z]\d+(?:\.\d+)*[.)]" + _TAIL),
    # (i)  (a)
    re.compile(r"[(（]" + _LETTER_OR_ROMAN + r"[)）]" + _TAIL),
    # A.  IV.
    re.compile(_LETTER_OR_ROMAN + r"[.)]" + _TAIL),
)
LIST_LABEL = re.compile(
    r"^(?:[ \t]*(?:>[ \t]?|[-*+][ \t]+|\d{1,9}[.)][ \t]+))*[ \t]*(?:\*\*|__|\*|_)?"
    r"(?P<label>[(（]" + _LETTER_OR_ROMAN + r"[)）]"
    r"|" + _LETTER_OR_ROMAN + r"[.)]"
    r"|\d+(?:\.\d+)*[A-Za-z][.)]"
    r"|\d+(?:\.\d+)*" + _PAREN_LETTERS +
    r"|\d+(?:\.\d+)*[a-gA-CE-G](?=[ \t]))" + _TAIL)
TABLE_LABEL = re.compile(r"\d+(?:\.\d+)*(?:" + _SUFFIX + r"|" + _PAREN_LETTERS + r")"
                         r"|[(（](?:[A-Za-z]|[ivxlc]{2,5})[)）]")
_INLINE_LETTER = r"[(（](?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)[)）]"
INLINE_LABEL = re.compile(
    r"(?<![A-Za-z0-9_)\]])(?<![A-Za-z0-9_]\*)" + _INLINE_LETTER +
    r"(?=[\s*_,.;:/!?]|$|[^\x00-\x7f])")
# Mid-line 26.5(a), ISSUE-3(a), 2.1(ii): the number must not continue a word, an index or a
# version (E_2(c), x2(b), v2.1(a) and f(2)(a) stay silent).
INLINE_DIGIT_LABEL = re.compile(
    r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)*(?:" + _INLINE_LETTER + r")+(?![A-Za-z0-9])")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
SHA_RE = re.compile(r"[0-9a-f]{16}")
COUNT_RE = re.compile(r"[1-9][0-9]*")

BLIND_SPOTS = [
    "Line-oriented: an ID and its name must sit on one line; a name wrapped onto the next "
    "line is reported, and a code span that continues across lines is masked on its first "
    "line only.",
    "Letter names (附录 B, 附表 A, 缺陷 A) and bare 2a without a section marker are not "
    "reported; see the rule list in repo_ledger/naming.py.",
    "HTML comments, link destinations and indented code blocks are scanned as prose.",
]


@dataclass
class NamingHit:
    line: int
    column: int
    token: str
    kind: str
    entity: str = ""
    name: str = ""


@dataclass
class BaselineRow:
    check: str
    file: str
    sha: str
    count: int
    line: int


def line_digest(line):
    """Stable 64-bit identity of one line of text; trailing whitespace and CR ignored."""
    return hashlib.sha256(line.rstrip().encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- masking

def _mask_inline_code(line):
    out = list(line)
    i, n = 0, len(line)
    while i < n:
        if line[i] == "\\" and i + 1 < n and line[i + 1] == "`":
            i += 2
            continue
        if line[i] != "`":
            i += 1
            continue
        j = i
        while j < n and line[j] == "`":
            j += 1
        run, k, close = j - i, j, -1
        while k < n:
            if line[k] != "`":
                k += 1
                continue
            m = k
            while m < n and line[m] == "`":
                m += 1
            if m - k == run:
                close = k
                break
            k = m
        if close < 0:
            i = j
            continue
        for p in range(i, close + run):
            out[p] = " "
        i = close + run
    return "".join(out)


def mask_markdown(lines):
    """Blank fenced blocks and inline code spans, preserving every column."""
    masked, fence = [], None
    for line in lines:
        match = FENCE.match(line)
        if fence:
            if (match and match.group(1)[0] == fence[0] and len(match.group(1)) >= fence[1]
                    and not match.group(2).strip()):
                fence = None
            masked.append(" " * len(line))
            continue
        if match and not (match.group(1)[0] == "`" and "`" in match.group(2)):
            fence = (match.group(1)[0], len(match.group(1)))
            masked.append(" " * len(line))
            continue
        masked.append(_mask_inline_code(line))
    return masked


# --------------------------------------------------------------------------- full names

def _ascii_alnum(ch):
    return ch.isascii() and ch.isalnum()


def _strip_cell(text):
    text = text.strip()
    changed = True
    while changed:
        changed = False
        for mark in ("**", "__", "*", "_"):
            if len(text) > 2 * len(mark) and text.startswith(mark) and text.endswith(mark):
                text = text[len(mark):-len(mark)].strip()
                changed = True
    return text


def _cell_spans(line):
    pipes = [i for i, ch in enumerate(line) if ch == "|" and (i == 0 or line[i - 1] != "\\")]
    spans = [(pipes[k] + 1, pipes[k + 1]) for k in range(len(pipes) - 1)]
    if pipes and line[pipes[-1] + 1:].strip():
        spans.append((pipes[-1] + 1, len(line)))
    return spans


def _name_after(after, variants):
    for closer in EMPHASIS:
        if not after.startswith(closer):
            continue
        rest = after[len(closer):]
        for space in SPACES:
            if not rest.startswith(space):
                continue
            tail = rest[len(space):]
            for opener in EMPHASIS:
                if not tail.startswith(opener):
                    continue
                text = tail[len(opener):]
                for name in variants:
                    if text.startswith(name):
                        following = text[len(name):len(name) + 1]
                        if not (_ascii_alnum(name[-1]) and following and _ascii_alnum(following)):
                            return True
    return False


def _name_before(before, variants):
    for opener in EMPHASIS:
        if opener and not before.endswith(opener):
            continue
        head = before[:len(before) - len(opener)]
        if not head.endswith(OPEN_PARENS):
            continue
        head = head[:-1]
        for space in SPACES:
            if space and not head.endswith(space):
                continue
            text = head[:len(head) - len(space)]
            for closer in EMPHASIS:
                if closer and not text.endswith(closer):
                    continue
                body = text[:len(text) - len(closer)]
                for name in variants:
                    if body.endswith(name):
                        preceding = body[len(body) - len(name) - 1:len(body) - len(name)]
                        if not (_ascii_alnum(name[0]) and preceding and _ascii_alnum(preceding)):
                            return True
    return False


def _table_adjacent(line, start, end, token, variants):
    if not line.lstrip().startswith("|"):
        return False
    spans = _cell_spans(line)
    for index, (left, right) in enumerate(spans):
        if left <= start and end <= right:
            if _strip_cell(line[left:right]) != token:
                return False
            neighbours = spans[max(index - 1, 0):index] + spans[index + 1:index + 2]
            return any(_strip_cell(line[a:b]) in variants for a, b in neighbours)
    return False


# The one hyphenated form that is not a mention: a machine run id <TYPE-N>-<skill>-<YYYYMMDD>
# (skill = lowercase letter, then lowercase letters, digits and single hyphens; a real
# calendar-shaped date; nothing word-like glued after it).
RUN_ID_TAIL = (r"-[a-z][a-z0-9]*(?:-[a-z0-9]+)*-\d{4}(?:0[1-9]|1[0-2])(?:0[1-9]|[12][0-9]|3[01])"
               r"(?![A-Za-z0-9_\-])")


def _id_pattern(types, display_prefixes):
    """An ID is a mention unless glued to an ASCII letter or digit; "_" and "-" are boundaries
    (underscore emphasis, RULE-6-clean), except an exact run id (RUN_ID_TAIL)."""
    if not types:
        return None
    canon = "|".join(re.escape(t) for t in sorted(types, key=len, reverse=True))
    parts = [rf"(?P<canon>{canon})-(?P<num>[0-9]+)"]
    if display_prefixes:
        disp = "|".join(re.escape(p) for p in sorted(display_prefixes, key=len, reverse=True))
        parts.append(rf"(?P<disp>{disp})-(?P<dnum>[0-9]+)")
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(parts) + r")(?![A-Za-z0-9])(?!"
                      + RUN_ID_TAIL + ")")


def _full_name_hits(lines, masked, names, pattern, display_prefixes, former_names=None):
    """former_names (entity -> names it carried earlier) is passed for historical text only."""
    hits = []
    if pattern is None:
        return hits
    former_names = former_names or {}
    for number, (raw, text) in enumerate(zip(lines, masked), 1):
        for match in pattern.finditer(text):
            if match.group("canon"):
                entity = f"{match.group('canon')}-{match.group('num')}"
            else:
                entity = f"{display_prefixes[match.group('disp')]}-{match.group('dnum')}"
            name = names.get(entity)
            if not name:
                continue
            token = match.group(0)
            variants = []
            for accepted in (name, *former_names.get(entity, ())):
                variants.append(accepted)
                if "|" in accepted:
                    variants.append(accepted.replace("|", "\\|"))
            start, end = match.span()
            if (_name_after(raw[end:], variants) or _name_before(raw[:start], variants)
                    or _table_adjacent(raw, start, end, token, variants)):
                continue
            hits.append(NamingHit(number, start + 1, token, "full_name", entity, name))
    return hits


def find_missing_full_names(lines, names, types, display_prefixes=None, former_names=None):
    """Mentions of registered entities that are not adjacent to their full name.

    Only the current name counts unless former_names is given; repository checks pass the
    registry's former names for historical files only, and the chat hook never does."""
    lines = list(lines)
    prefixes = dict(display_prefixes or {})
    return _full_name_hits(lines, mask_markdown(lines), names, _id_pattern(types, prefixes), prefixes,
                           former_names)


# --------------------------------------------------------------------------- former names

_COMMIT_LINE = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
_BATCH_HEADER = re.compile(rb"([0-9a-f]{40}(?:[0-9a-f]{24})?) ([a-z]+) ([0-9]+)")


def _has_head(root):
    try:
        git(root, "rev-parse", "--verify", "--quiet", "HEAD")
    except LedgerError:
        return False
    return True


def _blobs(root, specs):
    """UTF-8 texts of the given <commit>:<path> objects in one git cat-file --batch call."""
    if not specs:
        return []
    result = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"],
                            input=("\n".join(specs) + "\n").encode("utf-8"), capture_output=True)
    if result.returncode:
        raise LedgerError("ERR_GIT", result.stderr.decode("utf-8", "replace").strip(),
                          f"{root}:1:1", category="incomplete")
    data, pos, texts = result.stdout, 0, []
    while pos < len(data):
        end = data.index(b"\n", pos)
        header = _BATCH_HEADER.fullmatch(data[pos:end])
        pos = end + 1
        if header is None:
            continue  # "<object> missing": nothing follows
        size = int(header.group(3))
        body = data[pos:pos + size]
        pos += size + 1
        if header.group(2) == b"blob":
            try:
                texts.append(body.decode("utf-8"))
            except UnicodeDecodeError:
                continue
    return texts


def _registry_names(text):
    """(id, name) pairs of one registry version; rows that do not parse contribute nothing."""
    fields, pairs = None, []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        try:
            cells = _split_row_cells(line)
        except LedgerError:
            continue
        if fields is None:
            fields = LAYOUTS.get(tuple(cells))
            continue
        if len(cells) != len(fields):
            continue
        row = dict(zip(fields, cells))
        if ID_RE.fullmatch(row["id"]) and row["name"]:
            pairs.append((row["id"], row["name"]))
    return pairs


def former_names(root, registry_path, current):
    """Names each entity carried in committed versions of the registry, other than today's.

    Every committed version of the registry file (git log --follow, so a moved registry keeps
    its history) is read with its own header; a registered ID therefore keeps every name it
    was ever registered under.  Only historical text may use them: a line written before a
    rename stays compliant, while live files and chat replies need the current name."""
    if not _has_head(root):
        return {}
    log = git(root, "-c", "core.quotePath=false", "log", "--follow", "--format=%H", "--name-only",
              "--", registry_path)
    specs, commit = [], None
    for line in log.splitlines():
        line = line.strip()
        if not line:
            continue
        if _COMMIT_LINE.fullmatch(line):
            commit = line
        elif commit:
            specs.append(f"{commit}:{line}")
            commit = None
    names = {}
    for text in _blobs(root, specs):
        for entity, name in _registry_names(text):
            if entity in current and name != current[entity]:
                names.setdefault(entity, set()).add(name)
    return {entity: sorted(values) for entity, values in sorted(names.items())}


# --------------------------------------------------------------------------- letter labels

def _label_candidates(text):
    found = []  # (start, end, priority, token, kind)
    for regex in SECTION_RES:
        for match in regex.finditer(text):
            found.append((match.start(), match.end(), 0, match.group(0), "section"))
    for match in STEP_RE.finditer(text):
        found.append((match.start(), match.end(), 0, match.group(0), "step"))
    heading = HEADING_START.match(text)
    if heading:
        for regex in HEADING_LABELS:
            match = regex.match(text, heading.end())
            if match:
                found.append((match.start(), match.end(), 1, match.group(0), "heading"))
                break
    else:
        match = LIST_LABEL.match(text)
        if match:
            found.append((match.start("label"), match.end("label"), 2, match.group("label"), "list"))
    if text.lstrip().startswith("|"):
        spans = _cell_spans(text)
        if spans:
            left, right = spans[0]
            content = _strip_cell(text[left:right])
            if content and TABLE_LABEL.fullmatch(content):
                start = text.index(content, left)
                found.append((start, start + len(content), 3, content, "table"))
    for regex in (INLINE_LABEL, INLINE_DIGIT_LABEL):
        for match in regex.finditer(text):
            found.append((match.start(), match.end(), 4, match.group(0), "inline"))
    found.sort(key=lambda item: (item[0], item[2]))
    kept = []
    for item in found:
        if any(item[0] < end and start < item[1] for start, end, *_ in kept):
            continue
        kept.append(item)
    return kept


def _letter_hits(masked):
    hits = []
    for number, text in enumerate(masked, 1):
        for start, _end, _priority, token, kind in _label_candidates(text):
            hits.append(NamingHit(number, start + 1, token.strip(), kind))
    return hits


def find_letter_labels(lines):
    """Section, heading, list, table and inline ordinals that contain letters."""
    return _letter_hits(mask_markdown(list(lines)))


# --------------------------------------------------------------------------- baseline

def _baseline_error(reason, location):
    return LedgerError("ERR_NAMING_BASELINE", reason, location, category="configuration")


def parse_baseline(text, label):
    """Strictly parse a baseline; any malformed line fails closed."""
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != BASELINE_HEADER:
        raise _baseline_error(
            f"First line must be exactly '{BASELINE_HEADER}' (rules version "
            f"{NAMING_RULES_VERSION}); a new baseline is allowed only when the rules version changes",
            f"{label}:1:1")
    rows, seen, columns = [], set(), False
    for number, raw in enumerate(lines[1:], 2):
        line = raw.rstrip("\r")
        if not columns:
            if line.startswith("#"):
                continue
            if line != BASELINE_COLUMNS:
                raise _baseline_error(f"Expected the column header '{BASELINE_COLUMNS}'",
                                      f"{label}:{number}:1")
            columns = True
            continue
        fields = line.split("\t")
        if len(fields) != 4:
            raise _baseline_error("Expected four tab-separated fields", f"{label}:{number}:1")
        check, file, sha, count = fields
        if check not in CHECKS:
            raise _baseline_error(f"Unknown check {check!r}; expected one of {', '.join(CHECKS)}",
                                  f"{label}:{number}:1")
        if not relative_path(file):
            raise _baseline_error(f"Unsafe or non-relative path {file!r}", f"{label}:{number}:1")
        if not SHA_RE.fullmatch(sha):
            raise _baseline_error("line_sha256 must be 16 lowercase hexadecimal characters",
                                  f"{label}:{number}:1")
        if not COUNT_RE.fullmatch(count):
            raise _baseline_error("count must be a positive integer without leading zeros",
                                  f"{label}:{number}:1")
        if (check, file, sha) in seen:
            raise _baseline_error("Duplicate baseline row", f"{label}:{number}:1")
        seen.add((check, file, sha))
        rows.append(BaselineRow(check, file, sha, int(count), number))
    if not columns:
        raise _baseline_error(f"Missing the column header '{BASELINE_COLUMNS}'", f"{label}:1:1")
    return rows


def _ratchet(root, path, rows):
    """Compare the worktree rows with the first committed version under these rules."""
    info = {"status": "not committed", "root_commit": "", "skipped_versions": [], "growth_rows": 0}
    try:
        git(root, "rev-parse", "--verify", "--quiet", "HEAD")
    except LedgerError:
        return info, []  # no commit yet, so nothing is committed
    log = git(root, "log", "--full-history", "--reverse", "--format=%H", "--", path)
    commits = [commit for commit in log.split() if commit]
    if not commits:
        return info, []
    root_rows = None
    for commit in commits:
        try:
            text = git(root, "show", f"{commit}:{path}")
        except LedgerError:
            continue  # the path does not exist in this commit (deleted there)
        try:
            root_rows = parse_baseline(text, f"{commit[:8]}:{path}")
        except LedgerError as exc:
            info["skipped_versions"].append({"commit": commit[:8], "reason": exc.issue.reason})
            continue
        info["root_commit"] = commit
        break
    if root_rows is None:
        info["status"] = "no committed version under the current rules"
        return info, []
    allowance = Counter()
    for row in root_rows:
        allowance[(row.check, row.sha)] += row.count
    issues = []
    for row in rows:
        key = (row.check, row.sha)
        if allowance[key] >= row.count:
            allowance[key] -= row.count
            continue
        allowance[key] = 0
        issues.append(Issue(
            "ERR_NAMING_BASELINE_GROWTH", f"{path}:{row.line}:1", "",
            f"Baseline row exceeds the first committed baseline ({info['root_commit'][:8]}); "
            "rows may only be removed",
            "Fix the new text instead of baselining it; the baseline only shrinks."))
    info["status"] = "verified"
    info["growth_rows"] = len(issues)
    return info, issues


# --------------------------------------------------------------------------- repository scan

def _matches(rel, patterns):
    return any(fnmatch.fnmatchcase(rel, p) or (p.startswith("**/") and fnmatch.fnmatchcase(rel, p[3:]))
               for p in patterns)


def _collect(root, registry, force=False):
    """Hits of both guards; force evaluates a guard that is still switched off."""
    cfg = registry.config
    full, labels, baseline = cfg.full_name_guard, cfg.letter_label_guard, cfg.naming_baseline
    full_on, labels_on = full.enabled or force, labels.enabled or force
    audit = {
        "status": "enabled" if (full_on or labels_on) else "disabled",
        "rules_version": NAMING_RULES_VERSION,
        "full_name_guard": {"enabled": full.enabled, "scope_globs": list(full.scope_globs),
                            "exclude_globs": list(full.exclude_globs),
                            "display_prefixes": dict(full.display_prefixes), "scanned": [],
                            "hits": 0, "reported": 0,
                            "former_names": {"source": f"committed history of {cfg.registry_path}",
                                             "applies_to": "historical files (history_globs "
                                                           "minus live_globs)",
                                             "entities": 0, "names": 0}},
        "letter_label_guard": {"enabled": labels.enabled, "scope_globs": list(labels.scope_globs),
                               "exclude_globs": list(labels.exclude_globs), "scanned": [],
                               "hits": 0, "reported": 0},
        "baseline": {"path": baseline.path, "history_globs": list(baseline.history_globs),
                     "live_globs": list(baseline.live_globs), "rows": 0,
                     "suppressed": {"full_name": 0, "letter_label": 0}, "suppressed_by_file": {},
                     "stale_rows": 0, "scope_errors": 0, "ratchet": {"status": "no baseline"}},
        "excluded": [],
        "blind_spots": list(BLIND_SPOTS),
    }
    hits, issues = [], []
    if audit["status"] == "disabled":
        return hits, issues, audit
    names = {row.id: row.name for row in registry.rows}
    pattern = _id_pattern(cfg.types, full.display_prefixes)
    former = {}
    if full_on and baseline.history_globs:
        try:
            former = former_names(root, cfg.registry_path, names)
        except LedgerError as exc:
            issues.append(Issue(
                "ERR_NAMING_REGISTRY_HISTORY", f"{cfg.registry_path}:1:1", "", exc.issue.reason,
                "Run in a Git checkout with the registry history available; without it a renamed "
                "entity's historical lines cannot be checked.", "incomplete"))
        audit["full_name_guard"]["former_names"].update(
            entities=len(former), names=sum(len(values) for values in former.values()))
    tracked, new, _ = inventory(root)
    for rel in sorted(tracked | new):
        in_full = full_on and _matches(rel, full.scope_globs) and not _matches(rel, full.exclude_globs)
        in_labels = (labels_on and _matches(rel, labels.scope_globs)
                     and not _matches(rel, labels.exclude_globs))
        if not (in_full or in_labels):
            continue
        reason = None
        if rel == cfg.registry_path:
            reason = "authoritative registry parsed separately"
        elif rel == baseline.path:
            reason = "naming baseline"
        elif any(fnmatch.fnmatchcase(rel, p) for p in cfg.ignore_globs):
            reason = "configured ledger ignore"
        if reason:
            audit["excluded"].append({"file": rel, "reason": reason})
            continue
        try:
            lines = safe_file(root, rel).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError, LedgerError) as exc:
            issues.append(Issue("ERR_SCAN_INCOMPLETE", f"{rel}:1:1", "", str(exc),
                                "Restore a readable UTF-8 regular file in the repository.", "incomplete"))
            continue
        masked = mask_markdown(lines)
        if in_full:
            audit["full_name_guard"]["scanned"].append(rel)
            historical = former if _baselineable(rel, baseline) else None
            for hit in _full_name_hits(lines, masked, names, pattern, full.display_prefixes, historical):
                hits.append(("full_name", rel, line_digest(lines[hit.line - 1]), hit))
        if in_labels:
            audit["letter_label_guard"]["scanned"].append(rel)
            for hit in _letter_hits(masked):
                hits.append(("letter_label", rel, line_digest(lines[hit.line - 1]), hit))
    audit["full_name_guard"]["hits"] = sum(1 for h in hits if h[0] == "full_name")
    audit["letter_label_guard"]["hits"] = sum(1 for h in hits if h[0] == "letter_label")
    return hits, issues, audit


def _baselineable(rel, baseline):
    return _matches(rel, baseline.history_globs) and not _matches(rel, baseline.live_globs)


def _issue_for(check, rel, hit):
    location = f"{rel}:{hit.line}:{hit.column}"
    if check == "full_name":
        return Issue(
            "ERR_MISSING_FULL_NAME", location, hit.entity,
            f"User-facing mention lacks the full registered name; write '{hit.token} {hit.name}' "
            f"or '{hit.name}（{hit.token}）' on the same line",
            f"Run repo-ledger lookup {hit.entity} and copy the name exactly; code spans and fences "
            "are exempt.")
    return Issue(
        "ERR_LETTER_LABEL", location, "",
        f"Ordinal with a letter ({hit.kind} label): {hit.token}",
        "Number with digits only (levels as §2.1); refer to a thing by its ID and full name, "
        "and to a section together with its file name. Historical text is covered only by the "
        "committed naming baseline.")


def scan_naming(root, registry):
    """Run both naming guards and apply the ratchet baseline; read-only."""
    hits, issues, audit = _collect(root, registry)
    if audit["status"] == "disabled":
        return issues, audit
    cfg = registry.config
    baseline = cfg.naming_baseline
    base_audit = audit["baseline"]
    rows, present = [], False
    if baseline.path:
        path = safe_file(root, baseline.path)
        present = path.is_file()
        if present:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise _baseline_error(str(exc), f"{baseline.path}:1:1") from exc
            rows = parse_baseline(text, baseline.path)
        else:
            base_audit["ratchet"] = {"status": "baseline file absent"}
    base_audit["rows"] = len(rows)
    active = {"full_name": cfg.full_name_guard.enabled, "letter_label": cfg.letter_label_guard.enabled}
    budget = {}
    for row in rows:
        if not active[row.check]:
            continue
        if not _baselineable(row.file, baseline):
            base_audit["scope_errors"] += 1
            issues.append(Issue(
                "ERR_NAMING_BASELINE_SCOPE", f"{baseline.path}:{row.line}:1", "",
                f"Baseline row for {row.file}, which is not historical text "
                "(history_globs minus live_globs)",
                "Remove the row and fix the text; live files are never baselined."))
            continue
        budget[(row.check, row.file, row.sha)] = (row.count, row)
    used = Counter()
    for check, rel, sha, hit in hits:
        key = (check, rel, sha)
        entry = budget.get(key)
        if entry and used[key] < entry[0]:
            used[key] += 1
            base_audit["suppressed"][check] += 1
            base_audit["suppressed_by_file"][rel] = base_audit["suppressed_by_file"].get(rel, 0) + 1
            continue
        audit[f"{check}_guard"]["reported"] += 1
        issues.append(_issue_for(check, rel, hit))
    for key, (count, row) in budget.items():
        if used[key] < count:
            base_audit["stale_rows"] += 1
            issues.append(Issue(
                "ERR_NAMING_BASELINE_STALE", f"{baseline.path}:{row.line}:1", "",
                f"Baseline row for {row.file} covers {count} violation(s) but {used[key]} remain",
                "Delete or lower the row in the same change that fixed or edited the text."))
    if present:
        try:
            ratchet, growth = _ratchet(root, baseline.path, rows)
        except LedgerError as exc:
            ratchet, growth = {"status": "unavailable", "reason": exc.issue.reason}, [Issue(
                "ERR_NAMING_BASELINE_HISTORY", f"{baseline.path}:1:1", "", exc.issue.reason,
                "Run in a Git checkout with the baseline history available.", "incomplete")]
        base_audit["ratchet"] = ratchet
        issues.extend(growth)
    return issues, audit


def emit_baseline(root, registry):
    """Baseline text for today's violations in historical files (printed, never written).

    Both guards are evaluated even while switched off: a project prepares and commits its
    baseline before it switches the guards on."""
    hits, issues, _audit = _collect(root, registry, force=True)
    if issues:
        issue = issues[0]
        raise LedgerError(issue.code, issue.reason, issue.location, category=issue.category)
    baseline = registry.config.naming_baseline
    counts = Counter((check, rel, sha) for check, rel, sha, _hit in hits if _baselineable(rel, baseline))
    lines = [BASELINE_HEADER, BASELINE_COLUMNS]
    lines += [f"{check}\t{rel}\t{sha}\t{count}" for (check, rel, sha), count in sorted(counts.items())]
    return "\n".join(lines) + "\n"

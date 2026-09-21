"""Strict Markdown codec and serialized allocation in the main worktree."""
import datetime
import json
import os
from pathlib import Path
import re
import tempfile
import time
from dataclasses import asdict, dataclass

from .errors import LedgerError
from .git import repository_root, safe_file

TABLE_HEADER = ["id", "name", "status", "parent", "order", "anchor", "supersedes", "date", "note"]
RegistryError = LedgerError
ID_RE = re.compile(r"([A-Z][A-Z_]*)-([1-9][0-9]*)")

def encode(value):
    if value != value.strip() or any(ord(c) < 32 or c in "\x7f\x85\u2028\u2029" for c in value):
        raise LedgerError("ERR_INVALID_FIELD", "Fields cannot contain control characters or outer whitespace")
    return value.replace("\\", "\\\\").replace("|", "\\|")

def _split_row_cells(line):
    if not line.startswith("|") or not line.endswith("|"):
        raise LedgerError("ERR_ROW_FORMAT", "Expected a pipe-delimited row")
    cells, cell = [], []
    i = 1
    while i < len(line):
        char = line[i]
        if char == "\\":
            i += 1
            if i >= len(line) or line[i] not in ("\\", "|"):
                raise LedgerError("ERR_ESCAPE", f"Invalid escape at column {i}")
            cell.append(line[i])
        elif char == "|":
            cells.append("".join(cell).strip())
            cell = []
        else:
            cell.append(char)
        i += 1
    if cell or len(cells) != len(TABLE_HEADER):
        raise LedgerError("ERR_COLUMN_COUNT", f"Expected 9 columns, got {len(cells)}")
    for value in cells:
        encode(value)
    return cells

@dataclass
class EntityRow:
    id: str
    name: str
    status: str
    parent: str = ""
    order: str = ""
    anchor: str = ""
    supersedes: str = ""
    date: str = ""
    note: str = ""

    def to_dict(self):
        return asdict(self)

    def to_markdown_row(self):
        return "| " + " | ".join(encode(v) for v in asdict(self).values()) + " |"

def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as stream:
            temp = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp and temp.exists():
            temp.unlink()

class FileLock:
    def __init__(self, lock_path, timeout=10):
        self.path, self.timeout = lock_path, timeout

    def __enter__(self):
        start = time.monotonic()
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.monotonic() - start >= self.timeout:
                    raise LedgerError("ERR_LOCK_TIMEOUT", "Allocation lock is busy; inspect a possible crashed writer before removing the lock",
                                      f"{self.path}:1:1", category="incomplete")
                time.sleep(.02)

    def __exit__(self, *args):
        os.close(self.fd)
        self.path.unlink()

class EntityRegistry:
    def __init__(self, path, config):
        self.path, self.config = Path(path), config
        self.rows = []
        self.lines = {}
        self.preamble_lines = ["<!-- schema: 1.0 -->", "# Entity Registry", ""]

    @classmethod
    def load(cls, path, config):
        reg = cls(path, config)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise LedgerError("ERR_READ", str(exc), f"{path}:1:1", category="incomplete") from exc
        if not lines or lines[0] != "<!-- schema: 1.0 -->":
            raise LedgerError("ERR_SCHEMA", "First line must declare supported schema 1.0", f"{path}:1:1")
        header = None
        for n, line in enumerate(lines, 1):
            if re.match(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)", line):
                raise LedgerError("ERR_MERGE_CONFLICT", "Unresolved conflict marker", f"{path}:{n}:1")
            if n > 1 and "<!-- schema:" in line:
                raise LedgerError("ERR_SCHEMA", "Duplicate schema declaration", f"{path}:{n}:1")
            if line.startswith("|") and header is None:
                try:
                    cells = _split_row_cells(line)
                except LedgerError as exc:
                    exc.issue.location = f"{path}:{n}:1"
                    raise
                if cells != TABLE_HEADER:
                    raise LedgerError("ERR_HEADER", "Unexpected table header", f"{path}:{n}:1")
                header = n - 1
            elif header is None and n > 1 and line and not line.startswith(("# ", "> ")):
                raise LedgerError("ERR_ROW_FORMAT", "Unexpected content before table", f"{path}:{n}:1")
        if header is None or header + 1 >= len(lines):
            raise LedgerError("ERR_HEADER", "Missing header/separator", f"{path}:1:1")
        try:
            separator = _split_row_cells(lines[header + 1])
        except LedgerError as exc:
            exc.issue.location = f"{path}:{header+2}:1"
            raise
        if separator != ["---"] * 9:
            raise LedgerError("ERR_HEADER", "Expected nine --- separator cells", f"{path}:{header+2}:1")
        reg.preamble_lines = lines[:header]
        seen, serials = set(), {}
        for n in range(header + 2, len(lines)):
            if not lines[n].strip():
                continue
            row = None
            try:
                row = EntityRow(*_split_row_cells(lines[n]))
                match = ID_RE.fullmatch(row.id)
                if not match or match[1] not in config.types:
                    raise LedgerError("ERR_INVALID_ID_FORMAT", "Unknown type or noncanonical ID")
                if row.id in seen:
                    raise LedgerError("ERR_DUPLICATE_ID", "Duplicate entity")
                typ, serial = match[1], int(match[2])
                if serial <= serials.get(typ, 0):
                    raise LedgerError("ERR_SERIAL_ORDER", "Rows must increase per type")
                if not config.allow_gaps and serial != serials.get(typ, 0) + 1:
                    raise LedgerError("ERR_SERIAL_GAP", "Gap prohibited by configuration; never reuse issued IDs")
                if not row.name or not row.date or row.order != str(serial):
                    raise LedgerError("ERR_INVALID_FIELD", "name/date required; order must equal ID serial")
                try:
                    if datetime.date.fromisoformat(row.date).isoformat() != row.date:
                        raise ValueError()
                except ValueError:
                    raise LedgerError("ERR_INVALID_FIELD", "date must be YYYY-MM-DD")
                if row.status not in config.types[typ].allowed_statuses:
                    raise LedgerError("ERR_INVALID_STATUS", "Status is not in the type vocabulary")
                if row.parent and not ID_RE.fullmatch(row.parent):
                    raise LedgerError("ERR_INVALID_RELATION", "parent must be one ID")
                targets = row.supersedes.split(",") if row.supersedes else []
                if any(not ID_RE.fullmatch(t.strip()) for t in targets) or len(set(t.strip() for t in targets)) != len(targets):
                    raise LedgerError("ERR_INVALID_RELATION", "supersedes must contain distinct comma-separated IDs")
                if config.types[typ].require_anchor and not row.anchor:
                    raise LedgerError("ERR_MISSING_ANCHOR", "anchor is required")
                seen.add(row.id)
                serials[typ] = serial
                reg.rows.append(row)
                reg.lines[row.id] = n + 1
            except LedgerError as exc:
                exc.issue.location = f"{path}:{n+1}:1"
                exc.issue.entity = row.id if row is not None else ""
                raise
        return reg

    def save(self):
        text = "\n".join(self.preamble_lines + [
            "| " + " | ".join(TABLE_HEADER) + " |",
            "| " + " | ".join(["---"] * 9) + " |",
            *(row.to_markdown_row() for row in self.rows), ""])
        atomic_write(self.path, text)

    def lookup(self, entity_id):
        return next((row for row in self.rows if row.id == entity_id), None)

    def allocate(self, type_name, name="", status=None, parent="", anchor="", supersedes="", note=""):
        from .linter import check_registry_invariants
        root = self.path.resolve()
        for _ in Path(self.config.registry_path).parts:
            root = root.parent
        repository_root(root)
        # Linked worktrees and separate Git directories cannot mint in this release.
        if not (root / ".git").is_dir():
            raise LedgerError("ERR_ALLOCATION_WORKTREE", "Allocate only in the authoritative main worktree")
        safe_file(root, self.config.registry_path)
        state_path = root / ".git" / "repo-ledger-serials.json"
        with FileLock(root / ".git" / "repo-ledger-allocate.lock"):
            fresh = self.load(self.path, self.config)
            self.rows, self.lines, self.preamble_lines = fresh.rows, fresh.lines, fresh.preamble_lines
            if type_name not in self.config.types:
                raise LedgerError("ERR_INVALID_ID_FORMAT", "Unknown entity type")
            issues = check_registry_invariants(self, root)
            if issues:
                raise LedgerError(issues[0].code, issues[0].reason, issues[0].location, issues[0].entity)
            state = {}
            if state_path.exists():
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                    if not isinstance(state, dict) or any(not isinstance(k, str) or type(v) is not int or v < 0 for k, v in state.items()):
                        raise ValueError("Invalid allocation high-water marks")
                except (ValueError, UnicodeError) as exc:
                    raise LedgerError("ERR_ALLOCATION_STATE", str(exc), f"{state_path}:1:1")
            for row in self.rows:
                typ, number = row.id.rsplit("-", 1)
                state[typ] = max(state.get(typ, 0), int(number))
            serial = state.get(type_name, 0) + 1
            row = EntityRow(f"{type_name}-{serial}", name, status or self.config.types[type_name].allowed_statuses[0],
                            parent, str(serial), anchor, supersedes, datetime.date.today().isoformat(), note)
            # Validate the exact serialized candidate before either durable write.
            row.to_markdown_row()
            if not name or row.status not in self.config.types[type_name].allowed_statuses:
                raise LedgerError("ERR_INVALID_STATUS" if name else "ERR_INVALID_FIELD", "Supply a name and legal status", entity=row.id)
            if parent and not ID_RE.fullmatch(parent):
                raise LedgerError("ERR_INVALID_RELATION", "parent must be one ID", entity=row.id)
            targets = [s.strip() for s in supersedes.split(",")] if supersedes else []
            if len(set(targets)) != len(targets) or any(not ID_RE.fullmatch(t) for t in targets):
                raise LedgerError("ERR_INVALID_RELATION", "Invalid supersedes list", entity=row.id)
            self.rows.append(row)
            issues = check_registry_invariants(self, root)
            if issues:
                raise LedgerError(issues[0].code, issues[0].reason, issues[0].location, issues[0].entity)
            state[type_name] = serial
            atomic_write(state_path, json.dumps(state, indent=2) + "\n")
            self.save()
            return row

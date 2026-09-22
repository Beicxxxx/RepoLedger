"""Strict Markdown codec and serialized allocation in the main worktree."""
import datetime
import json
import os
from pathlib import Path
import re
import tempfile
import time
from dataclasses import asdict, dataclass, replace

from .config import LedgerConfig
from .errors import LedgerError
from .git import repository_root, safe_file

TABLE_HEADER = ["id", "name", "status", "parent", "order", "anchor", "supersedes", "date", "legacy", "note"]
OWNER_TABLE_HEADER = ["id", "name", "status", "parent", "order", "owner", "legacy", "supersedes", "date", "note"]
LEGACY_TABLE_HEADER = ["id", "name", "status", "parent", "order", "anchor", "supersedes", "date", "note"]
# Field order per accepted layout. "owner" and "anchor" name the same column: the evidence
# carrier. RepoLedger writes the canonical layout; it reads the project layouts it was
# told about, and never guesses an unknown header.
CANONICAL_FIELDS = ("id", "name", "status", "parent", "order", "anchor", "supersedes", "date", "legacy", "note")
OWNER_FIELDS = ("id", "name", "status", "parent", "order", "anchor", "legacy", "supersedes", "date", "note")
LEGACY_FIELDS = ("id", "name", "status", "parent", "order", "anchor", "supersedes", "date", "note")
LAYOUTS = {
    tuple(TABLE_HEADER): CANONICAL_FIELDS,
    tuple(OWNER_TABLE_HEADER): OWNER_FIELDS,
    tuple(LEGACY_TABLE_HEADER): LEGACY_FIELDS,
}
RegistryError = LedgerError
ID_RE = re.compile(r"([A-Z][A-Z_]*)-([1-9][0-9]*)")
ORDER_RE = re.compile(r"[1-9][0-9]*")

def encode(value):
    if value != value.strip() or any(ord(c) < 32 or c in "\x7f\x85\u2028\u2029" for c in value):
        raise LedgerError("ERR_INVALID_FIELD", "Fields cannot contain control characters or outer whitespace")
    return value.replace("\\", "\\\\").replace("|", "\\|")


def format_row(row, fields=CANONICAL_FIELDS):
    """Serialize a row in the given layout; the writer always encodes field content."""
    values = asdict(row)
    return "| " + " | ".join(encode(values[field]) for field in fields) + " |"

def _split_row_cells(line, expected_columns=None):
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
    if cell or (expected_columns is not None and len(cells) != expected_columns):
        expected = expected_columns if expected_columns is not None else "a valid number of"
        raise LedgerError("ERR_COLUMN_COUNT", f"Expected {expected} columns, got {len(cells)}")
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
    legacy: str = ""

    def to_dict(self):
        return asdict(self)

    def to_markdown_row(self):
        return format_row(self)

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
        self.fields = CANONICAL_FIELDS
        self.table_header = list(TABLE_HEADER)

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
        table_header = None
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
                if tuple(cells) not in LAYOUTS:
                    raise LedgerError("ERR_HEADER", "Unexpected table header", f"{path}:{n}:1")
                table_header = cells
                fields = LAYOUTS[tuple(cells)]
                header = n - 1
            elif header is None and n > 1 and line and not line.startswith(("# ", "> ")):
                raise LedgerError("ERR_ROW_FORMAT", "Unexpected content before table", f"{path}:{n}:1")
        if header is None or header + 1 >= len(lines):
            raise LedgerError("ERR_HEADER", "Missing header/separator", f"{path}:1:1")
        try:
            separator = _split_row_cells(lines[header + 1], len(table_header))
        except LedgerError as exc:
            exc.issue.location = f"{path}:{header+2}:1"
            raise
        if separator != ["---"] * len(table_header):
            raise LedgerError("ERR_HEADER", f"Expected {len(table_header)} --- separator cells", f"{path}:{header+2}:1")
        reg.preamble_lines = lines[:header]
        reg.table_header = list(table_header)
        reg.fields = fields
        seen, seen_legacy, serials = set(), set(), {}
        seen_order = {}
        for n in range(header + 2, len(lines)):
            if not lines[n].strip():
                continue
            row = None
            try:
                cells = _split_row_cells(lines[n], len(table_header))
                values = {field: cells[index] for index, field in enumerate(fields)}
                values.setdefault("legacy", "")
                row = EntityRow(**values)
                match = ID_RE.fullmatch(row.id)
                if not match or match[1] not in config.types:
                    raise LedgerError("ERR_INVALID_ID_FORMAT", "Unknown type or noncanonical ID")
                if row.id in seen:
                    raise LedgerError("ERR_DUPLICATE_ID", "Duplicate entity")
                if row.id in seen_legacy:
                    raise LedgerError("ERR_LEGACY_COLLISION", "A current ID cannot also be a legacy alias")
                if row.legacy and row.legacy in seen_legacy:
                    raise LedgerError("ERR_DUPLICATE_LEGACY", "A legacy alias must identify at most one entity")
                if row.legacy and (row.legacy in seen or row.legacy == row.id):
                    raise LedgerError("ERR_LEGACY_COLLISION", "A legacy alias cannot also be a current ID")
                typ, serial = match[1], int(match[2])
                if serial <= serials.get(typ, 0):
                    raise LedgerError("ERR_SERIAL_ORDER", "Rows must increase per type")
                if not config.allow_gaps and serial != serials.get(typ, 0) + 1:
                    raise LedgerError("ERR_SERIAL_GAP", "Gap prohibited by configuration; never reuse issued IDs")
                if not row.name or not row.date:
                    raise LedgerError("ERR_INVALID_FIELD", "name and date are required")
                if config.independent_order:
                    # order is a render-only plan position, never an identity or status signal.
                    if not ORDER_RE.fullmatch(row.order):
                        raise LedgerError("ERR_INVALID_ORDER",
                                          "order must be a positive integer without leading zeros")
                    if config.unique_order_within_scope:
                        scope = (typ, row.parent, row.order)
                        if scope in seen_order:
                            raise LedgerError(
                                "ERR_DUPLICATE_ORDER",
                                f"order {row.order} is already used by {seen_order[scope]} "
                                "in the same type and parent scope")
                        seen_order[scope] = row.id
                elif row.order != str(serial):
                    raise LedgerError("ERR_INVALID_FIELD",
                                      "order must equal the ID serial unless independent_order is enabled")
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
                if row.legacy:
                    seen_legacy.add(row.legacy)
                serials[typ] = serial
                reg.rows.append(row)
                reg.lines[row.id] = n + 1
            except LedgerError as exc:
                exc.issue.location = f"{path}:{n+1}:1"
                exc.issue.entity = row.id if row is not None else ""
                raise
        return reg

    def save(self):
        # A nine-column registry upgrades on first save; recognised ten-column layouts are kept.
        upgrading = self.table_header == LEGACY_TABLE_HEADER
        header = list(TABLE_HEADER) if upgrading else list(self.table_header)
        fields = CANONICAL_FIELDS if upgrading else self.fields
        text = "\n".join(self.preamble_lines + [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * len(header)) + " |",
            *(format_row(row, fields) for row in self.rows), ""])
        self.table_header, self.fields = header, fields
        atomic_write(self.path, text)

    def lookup(self, entity_id):
        return next((row for row in self.rows if row.id == entity_id or (entity_id and row.legacy == entity_id)), None)

    def _main_worktree_root(self, operation="allocate"):
        root = self.path.resolve()
        for _ in Path(self.config.registry_path).parts:
            root = root.parent
        repository_root(root)
        # Linked worktrees and separate Git directories cannot write in this release.
        if not (root / ".git").is_dir():
            action = "Allocate" if operation == "allocate" else "Update"
            raise LedgerError("ERR_ALLOCATION_WORKTREE", f"{action} only in the authoritative main worktree")
        safe_file(root, self.config.registry_path)
        return root

    def _next_order(self, type_name, parent):
        used = [int(row.order) for row in self.rows
                if row.parent == parent and row.id.rsplit("-", 1)[0] == type_name
                and ORDER_RE.fullmatch(row.order)]
        return max(used, default=0) + 1

    def allocate(self, type_name, name="", status=None, parent="", anchor="", supersedes="",
                 note="", legacy="", order=None):
        from .linter import check_registry_invariants
        root = self._main_worktree_root()
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
            if not self.config.independent_order:
                if order is not None:
                    raise LedgerError("ERR_ORDER_FIXED",
                                      "--order requires independent_order = true in ledger.toml")
                planned = str(serial)
            elif order is None:
                planned = str(self._next_order(type_name, parent))
            elif not ORDER_RE.fullmatch(order):
                raise LedgerError("ERR_INVALID_ORDER",
                                  "--order must be a positive integer without leading zeros")
            else:
                planned = order
            row = EntityRow(f"{type_name}-{serial}", name, status or self.config.types[type_name].allowed_statuses[0],
                            parent, planned, anchor, supersedes, datetime.date.today().isoformat(), note, legacy)
            # Validate the exact serialized candidate before either durable write.
            format_row(row, self.fields)
            if not name or row.status not in self.config.types[type_name].allowed_statuses:
                raise LedgerError("ERR_INVALID_STATUS" if name else "ERR_INVALID_FIELD", "Supply a name and legal status", entity=row.id)
            if legacy and any(existing.legacy == legacy for existing in self.rows):
                raise LedgerError("ERR_DUPLICATE_LEGACY", "A legacy alias must identify at most one entity", entity=row.id)
            if legacy and any(existing.id == legacy for existing in self.rows):
                raise LedgerError("ERR_LEGACY_COLLISION", "A legacy alias cannot also be a current ID", entity=row.id)
            if any(existing.legacy == row.id for existing in self.rows):
                raise LedgerError("ERR_LEGACY_COLLISION", "A current ID cannot also be a legacy alias", entity=row.id)
            if parent and not ID_RE.fullmatch(parent):
                raise LedgerError("ERR_INVALID_RELATION", "parent must be one ID", entity=row.id)
            if self.config.independent_order and self.config.unique_order_within_scope:
                clash = next((existing for existing in self.rows
                              if existing.parent == parent
                              and existing.id.rsplit("-", 1)[0] == type_name
                              and existing.order == planned), None)
                if clash is not None:
                    raise LedgerError("ERR_DUPLICATE_ORDER",
                                      f"order {planned} is already used by {clash.id} "
                                      "in the same type and parent scope", entity=clash.id)
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

    def update(self, entity_id, *, status=None, note=None, order=None, expected_status=None):
        """Update mutable status, note and (when enabled) plan order under the allocation lock."""
        from .linter import check_registry_invariants

        if status is None and note is None and order is None:
            raise LedgerError("ERR_NO_UPDATE",
                              "Supply status, note, and/or order to update", entity=entity_id)

        root = self._main_worktree_root("update")
        with FileLock(root / ".git" / "repo-ledger-allocate.lock"):
            latest_config = LedgerConfig.load(root / "ledger.toml")
            latest_path = safe_file(root, latest_config.registry_path)
            if latest_path.resolve() != self.path.resolve():
                raise LedgerError("ERR_REGISTRY_PATH_CHANGED",
                                  "Registry path changed; reload the registry before updating",
                                  f"{root / 'ledger.toml'}:1:1", entity=entity_id)

            fresh = self.load(latest_path, latest_config)
            row_index = next((index for index, row in enumerate(fresh.rows)
                              if row.id == entity_id), None)
            if row_index is None:
                alias = next((row for row in fresh.rows if entity_id and row.legacy == entity_id), None)
                if alias is not None:
                    raise LedgerError("ERR_LEGACY_READONLY",
                                      f"Legacy alias is read-only; use current ID {alias.id}",
                                      f"{fresh.path}:{fresh.lines.get(alias.id, 1)}:1", entity=entity_id)
                raise LedgerError("ERR_UNREGISTERED_ENTITY", "Entity not found",
                                  f"{fresh.path}:1:1", entity=entity_id)

            row = fresh.rows[row_index]
            location = f"{fresh.path}:{fresh.lines.get(row.id, 1)}:1"
            if expected_status is not None and row.status != expected_status:
                raise LedgerError("ERR_UPDATE_CONFLICT",
                                  f"Expected status {expected_status!r}, found {row.status!r}",
                                  location, entity=row.id)

            type_name = row.id.rsplit("-", 1)[0]
            next_status = row.status if status is None else status
            next_note = row.note if note is None else note
            next_order = row.order
            if order is not None:
                if not latest_config.independent_order:
                    raise LedgerError("ERR_ORDER_FIXED",
                                      "order is fixed to the ID serial; enable independent_order to replan it",
                                      location, entity=row.id)
                if not ORDER_RE.fullmatch(order):
                    raise LedgerError("ERR_INVALID_ORDER",
                                      "order must be a positive integer without leading zeros",
                                      location, entity=row.id)
                clash = next((other for other in fresh.rows
                              if latest_config.unique_order_within_scope
                              and other.id != row.id and other.parent == row.parent
                              and other.id.rsplit("-", 1)[0] == type_name
                              and other.order == order), None)
                if clash is not None:
                    raise LedgerError("ERR_DUPLICATE_ORDER",
                                      f"order {order} is already used by {clash.id} "
                                      "in the same type and parent scope", location, entity=row.id)
                next_order = order
            if status is not None and (not isinstance(status, str)
                                       or status not in latest_config.types[type_name].allowed_statuses):
                raise LedgerError("ERR_INVALID_STATUS", "Status is not in the type vocabulary",
                                  location, entity=row.id)
            if note is not None and not isinstance(note, str):
                raise LedgerError("ERR_INVALID_FIELD", "note must be a string", location, row.id)
            if note is not None:
                try:
                    encode(note)
                except LedgerError as exc:
                    exc.issue.location = location
                    exc.issue.entity = row.id
                    raise

            candidate = replace(row, status=next_status, note=next_note, order=next_order)
            try:
                format_row(candidate, fresh.fields)
            except LedgerError as exc:
                exc.issue.location = location
                exc.issue.entity = row.id
                raise
            fresh.rows[row_index] = candidate
            issues = check_registry_invariants(fresh, root)
            if issues:
                issue = issues[0]
                raise LedgerError(issue.code, issue.reason, issue.location, issue.entity)

            fresh.save()
            self.path = fresh.path
            self.config = fresh.config
            self.rows = fresh.rows
            self.lines = fresh.lines
            self.preamble_lines = fresh.preamble_lines
            return candidate

"""Registry table parser, serializer, ID allocator, and short-lock mechanism."""
from __future__ import annotations

import datetime
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import LedgerConfig

TABLE_HEADER = ["id", "name", "status", "parent", "order", "anchor", "supersedes", "date", "note"]
SCHEMA_COMMENT_PREFIX = "<!-- schema: "
_ESCAPED_PIPE = "\x00ESCAPED_PIPE\x00"


class RegistryError(Exception):
    pass


class LockTimeoutError(RegistryError):
    pass


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

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "parent": self.parent,
            "order": self.order,
            "anchor": self.anchor,
            "supersedes": self.supersedes,
            "date": self.date,
            "note": self.note,
        }

    def to_markdown_row(self) -> str:
        vals = [
            self.id,
            self.name,
            self.status,
            self.parent,
            self.order,
            self.anchor,
            self.supersedes,
            self.date,
            self.note.replace("|", "\\|"),
        ]
        return "| " + " | ".join(vals) + " |"


def _split_row_cells(line: str) -> list[str]:
    protected = line.strip().replace("\\|", _ESCAPED_PIPE)
    cells = [c.strip().replace(_ESCAPED_PIPE, "|") for c in protected.strip("|").split("|")]
    return cells


class FileLock:
    """Short-lived file lock for serializing local allocations."""
    def __init__(self, lock_path: Path, timeout: float = 10.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
        start = time.time()
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                # O_CREAT | O_EXCL ensures atomic creation
                self.fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                return self
            except FileExistsError:
                if time.time() - start > self.timeout:
                    raise LockTimeoutError(
                        f"Timed out after {self.timeout}s waiting for allocation lock: {self.lock_path}"
                    )
                time.sleep(0.05)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            try:
                self.lock_path.unlink(missing_ok=True)
            except OSError:
                pass


class EntityRegistry:
    def __init__(self, path: Path, config: LedgerConfig):
        self.path = path
        self.config = config
        self.schema_version: str = "1.0"
        self.preamble_lines: list[str] = []
        self.rows: list[EntityRow] = []

    @classmethod
    def load(cls, path: Path, config: LedgerConfig) -> "EntityRegistry":
        reg = cls(path, config)
        if not path.is_file():
            return reg

        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()

        header_idx = None
        for i, line in enumerate(lines):
            # Parse schema version comment if present
            stripped = line.strip()
            if stripped.startswith(SCHEMA_COMMENT_PREFIX) and stripped.endswith("-->"):
                reg.schema_version = stripped[len(SCHEMA_COMMENT_PREFIX):-3].strip()

            cells = _split_row_cells(line)
            if cells == TABLE_HEADER:
                header_idx = i
                break

        if header_idx is None:
            raise RegistryError(
                f"Invalid registry format in {path}: header row {TABLE_HEADER!r} not found"
            )

        reg.preamble_lines = lines[:header_idx]

        # Scan rows after header and separator
        data_start = header_idx + 2
        for lineno, line in enumerate(lines[data_start:], start=data_start + 1):
            stripped = line.strip()
            if not stripped or not stripped.startswith("|"):
                continue
            cells = _split_row_cells(line)
            if len(cells) < len(TABLE_HEADER):
                raise RegistryError(
                    f"Corrupt registry row in {path}:{lineno}: expected {len(TABLE_HEADER)} columns, got {len(cells)}"
                )
            reg.rows.append(EntityRow(
                id=cells[0],
                name=cells[1],
                status=cells[2],
                parent=cells[3],
                order=cells[4],
                anchor=cells[5],
                supersedes=cells[6],
                date=cells[7],
                note=cells[8],
            ))
        return reg

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content_lines = list(self.preamble_lines)
        if not content_lines:
            content_lines = [
                f"<!-- schema: {self.config.schema_version} -->",
                "# Entity Registry Ledger",
                "",
                "> Authoritative ledger of canonical entity allocations.",
                "> Format: `TYPE-N` (strict monotonic serials, append-only).",
                "",
            ]

        # Ensure schema comment is in preamble
        has_schema = any(l.strip().startswith(SCHEMA_COMMENT_PREFIX) for l in content_lines)
        if not has_schema:
            content_lines.insert(0, f"<!-- schema: {self.config.schema_version} -->")

        # Add table header
        content_lines.append("| " + " | ".join(TABLE_HEADER) + " |")
        content_lines.append("| " + " | ".join(["---"] * len(TABLE_HEADER)) + " |")

        for r in self.rows:
            content_lines.append(r.to_markdown_row())

        text_to_write = "\n".join(content_lines) + "\n"

        # Atomic replacement via temporary file
        temp_dir = self.path.parent
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=temp_dir, delete=False) as tf:
            tf.write(text_to_write)
            temp_path = Path(tf.name)

        temp_path.replace(self.path)

    def lookup(self, entity_id: str) -> Optional[EntityRow]:
        target = entity_id.strip()
        for r in self.rows:
            if r.id == target:
                return r
        return None

    def get_max_serial(self, type_prefix: str) -> int:
        pattern = re.compile(rf"^{re.escape(type_prefix)}-([1-9][0-9]*)$")
        max_s = 0
        for r in self.rows:
            m = pattern.match(r.id)
            if m:
                max_s = max(max_s, int(m.group(1)))
        return max_s

    def allocate(
        self,
        type_name: str,
        name: str = "",
        status: Optional[str] = None,
        parent: str = "",
        anchor: str = "",
        supersedes: str = "",
        note: str = "",
    ) -> EntityRow:
        lock_path = self.path.parent / ".alloc.lock"
        with FileLock(lock_path):
            # Reload fresh inside lock to avoid racing concurrent local allocations
            if self.path.is_file():
                fresh = EntityRegistry.load(self.path, self.config)
                self.rows = fresh.rows
                self.preamble_lines = fresh.preamble_lines

            t_cfg = self.config.types.get(type_name)
            prefix = t_cfg.prefix if t_cfg else type_name

            next_serial = self.get_max_serial(prefix) + 1
            new_id = f"{prefix}-{next_serial}"

            default_status = status
            if not default_status:
                if t_cfg and t_cfg.allowed_statuses:
                    default_status = t_cfg.allowed_statuses[0]
                else:
                    default_status = "BACKLOG"

            today = datetime.date.today().isoformat()
            row = EntityRow(
                id=new_id,
                name=name or f"New {type_name}",
                status=default_status,
                parent=parent,
                order=str(next_serial),
                anchor=anchor,
                supersedes=supersedes,
                date=today,
                note=note,
            )
            self.rows.append(row)
            self.save()
            return row

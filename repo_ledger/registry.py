"""Registry table parser, serializer, and ID allocator."""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import LedgerConfig

TABLE_HEADER = ["id", "name", "status", "parent", "order", "owner", "supersedes", "date", "note"]
_ESCAPED_PIPE = "\x00ESCAPED_PIPE\x00"


@dataclass
class EntityRow:
    id: str
    name: str
    status: str
    parent: str = ""
    order: str = ""
    owner: str = ""
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
            "owner": self.owner,
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
            self.owner,
            self.supersedes,
            self.date,
            self.note.replace("|", "\\|"),
        ]
        return "| " + " | ".join(vals) + " |"


class RegistryError(Exception):
    pass


def _split_row_cells(line: str) -> list[str]:
    protected = line.strip().replace("\\|", _ESCAPED_PIPE)
    cells = [c.strip().replace(_ESCAPED_PIPE, "|") for c in protected.strip("|").split("|")]
    return cells


class EntityRegistry:
    def __init__(self, path: Path, config: LedgerConfig):
        self.path = path
        self.config = config
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
            cells = _split_row_cells(line)
            if cells == TABLE_HEADER:
                header_idx = i
                break

        if header_idx is None:
            # File exists but no table yet
            reg.preamble_lines = lines
            return reg

        reg.preamble_lines = lines[:header_idx]

        # Scan rows after header and separator
        data_start = header_idx + 2  # skip header and separator row
        for line in lines[data_start:]:
            stripped = line.strip()
            if not stripped or not stripped.startswith("|"):
                continue
            cells = _split_row_cells(line)
            if len(cells) < len(TABLE_HEADER):
                # Pad cells if missing
                cells += [""] * (len(TABLE_HEADER) - len(cells))
            reg.rows.append(EntityRow(
                id=cells[0],
                name=cells[1],
                status=cells[2],
                parent=cells[3],
                order=cells[4],
                owner=cells[5],
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
                "# Entity Registry Ledger",
                "",
                "> Authoritative ledger of canonical entity allocations.",
                "> Format: `TYPE-N` (strict monotonic serials, append-only).",
                "",
            ]

        # Add table header
        content_lines.append("| " + " | ".join(TABLE_HEADER) + " |")
        content_lines.append("| " + " | ".join(["---"] * len(TABLE_HEADER)) + " |")

        for r in self.rows:
            content_lines.append(r.to_markdown_row())

        self.path.write_text("\n".join(content_lines) + "\n", encoding="utf-8")

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
        owner: str = "",
        supersedes: str = "",
        note: str = "",
    ) -> EntityRow:
        t_cfg = self.config.types.get(type_name)
        prefix = t_cfg.prefix if t_cfg else type_name

        next_serial = self.get_max_serial(prefix) + 1
        new_id = f"{prefix}-{next_serial}"

        default_status = status
        if not default_status:
            if t_cfg and t_cfg.allowed_statuses:
                default_status = t_cfg.allowed_statuses[0]
            else:
                default_status = "READY"

        today = datetime.date.today().isoformat()
        row = EntityRow(
            id=new_id,
            name=name or f"New {type_name}",
            status=default_status,
            parent=parent,
            order=str(next_serial),
            owner=owner,
            supersedes=supersedes,
            date=today,
            note=note,
        )
        self.rows.append(row)
        return row

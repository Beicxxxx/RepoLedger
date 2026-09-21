"""Configuration loader and schema for RepoLedger."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        raise ImportError("Python 3.11+ is required, or install 'tomli' for Python 3.10.")


@dataclass
class EntityTypeConfig:
    prefix: str
    allowed_statuses: list[str] = field(default_factory=list)
    require_anchor: bool = True
    description: str = ""


@dataclass
class LedgerConfig:
    schema_version: str = "1.0"
    registry_path: str = ".ledger/ENTITY_REGISTRY.md"
    allow_gaps: bool = True  # Per V1 constraint: gaps are not errors by default
    doc_dirs: list[str] = field(default_factory=lambda: ["docs", ".ai/state", ".ai/handoff"])
    code_extensions: list[str] = field(default_factory=lambda: [".py", ".ts", ".js", ".go", ".rs", ".json"])
    ignore_globs: list[str] = field(default_factory=lambda: [
        "node_modules/**", "dist/**", "build/**", ".git/**", "tests/fixtures/**", "*.egg-info/**"
    ])
    types: dict[str, EntityTypeConfig] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "LedgerConfig":
        cfg = cls()
        # Minimal default types per RFC
        cfg.types = {
            "TASK": EntityTypeConfig(
                prefix="TASK",
                allowed_statuses=["BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE", "DROPPED"],
                require_anchor=True,
                description="Actionable engineering or research tasks",
            ),
            "DECISION": EntityTypeConfig(
                prefix="DECISION",
                allowed_statuses=["DRAFT", "IN_FORCE", "SUPERSEDED"],
                require_anchor=True,
                description="Architecture Decision Records and policy rulings",
            ),
            "ISSUE": EntityTypeConfig(
                prefix="ISSUE",
                allowed_statuses=["OPEN", "INVESTIGATING", "RESOLVED", "WONT_FIX"],
                require_anchor=True,
                description="Defects, regressions, and blockers",
            ),
        }
        return cfg

    @classmethod
    def load(cls, path: Path) -> "LedgerConfig":
        if not path.is_file():
            return cls.default()

        with open(path, "rb") as f:
            data = tomllib.load(f)

        ledger_section = data.get("ledger", {})
        schema_version = str(ledger_section.get("schema_version", "1.0"))
        registry_path = ledger_section.get("registry_path", ".ledger/ENTITY_REGISTRY.md")
        allow_gaps = bool(ledger_section.get("allow_gaps", True))
        doc_dirs = ledger_section.get("doc_dirs", ["docs", ".ai/state", ".ai/handoff"])
        code_extensions = ledger_section.get("code_extensions", [".py", ".ts", ".js", ".go", ".rs", ".json"])
        ignore_globs = ledger_section.get("ignore_globs", [
            "node_modules/**", "dist/**", "build/**", ".git/**", "tests/fixtures/**"
        ])

        types: dict[str, EntityTypeConfig] = {}
        types_section = data.get("types", {})
        if types_section:
            for type_name, t_data in types_section.items():
                types[type_name] = EntityTypeConfig(
                    prefix=t_data.get("prefix", type_name),
                    allowed_statuses=t_data.get("allowed_statuses", []),
                    require_anchor=t_data.get("require_anchor", True),
                    description=t_data.get("description", ""),
                )
        else:
            types = cls.default().types

        return cls(
            schema_version=schema_version,
            registry_path=registry_path,
            allow_gaps=allow_gaps,
            doc_dirs=doc_dirs,
            code_extensions=code_extensions,
            ignore_globs=ignore_globs,
            types=types,
        )


def find_config_file(start_dir: Optional[Path] = None) -> Optional[Path]:
    """Find ledger.toml or .ledger.toml in start_dir or parent directories."""
    curr = (start_dir or Path.cwd()).resolve()
    for directory in [curr] + list(curr.parents):
        for candidate in ["ledger.toml", ".ledger.toml", ".ledger/config.toml"]:
            p = directory / candidate
            if p.is_file():
                return p
        if (directory / ".git").is_dir():
            break
    return None

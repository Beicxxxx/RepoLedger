"""Strict Python 3.11+ TOML configuration."""
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import re
import tomllib
from .errors import LedgerError

def relative_path(value):
    return (isinstance(value, str) and bool(value) and "\\" not in value
            and ":" not in value and not PurePosixPath(value).is_absolute()
            and all(p not in ("", ".", "..", ".git") for p in value.split("/")))

@dataclass
class EntityTypeConfig:
    prefix: str
    allowed_statuses: list[str]
    require_anchor: bool = True
    description: str = ""

@dataclass
class LedgerConfig:
    schema_version: str = "1.0"
    registry_path: str = ".ledger/ENTITY_REGISTRY.md"
    allow_gaps: bool = True
    code_extensions: list[str] = field(default_factory=lambda: [".py", ".ts", ".js", ".go", ".rs", ".json", ".md"])
    ignore_globs: list[str] = field(default_factory=list)
    types: dict = field(default_factory=dict)

    @classmethod
    def default(cls):
        return cls(types={
            "TASK": EntityTypeConfig("TASK", ["BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE", "DROPPED"]),
            "DECISION": EntityTypeConfig("DECISION", ["DRAFT", "IN_FORCE", "SUPERSEDED"]),
            "ISSUE": EntityTypeConfig("ISSUE", ["OPEN", "INVESTIGATING", "RESOLVED", "WONT_FIX"]),
        })

    @classmethod
    def load(cls, path):
        def fail(reason):
            raise LedgerError("ERR_CONFIG", reason, f"{path}:1:1", category="configuration")
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            fail(str(exc))
        if set(data) - {"ledger", "types"}:
            fail("Unknown top-level configuration field")
        cfg = cls.default()
        section = data.get("ledger", {})
        allowed = {"schema_version", "registry_path", "allow_gaps", "code_extensions", "ignore_globs", "doc_dirs"}
        if not isinstance(section, dict) or set(section) - allowed:
            fail("Unknown ledger field (transition/evidence policies are not supported yet)")
        for key, value in section.items():
            if key == "doc_dirs":
                if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                    fail("doc_dirs must be a string array; retained for legacy compatibility")
                continue
            setattr(cfg, key, value)
        if cfg.schema_version != "1.0" or not relative_path(cfg.registry_path):
            fail("Expected schema 1.0 and a safe repository-relative registry_path")
        if type(cfg.allow_gaps) is not bool:
            fail("allow_gaps must be boolean")
        for key in ("code_extensions", "ignore_globs"):
            value = getattr(cfg, key)
            if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
                fail(f"{key} must be a string array")
        if not all(x.startswith(".") for x in cfg.code_extensions):
            fail("code_extensions entries must start with a dot")
        if "types" in data:
            if not isinstance(data["types"], dict) or not data["types"]:
                fail("types must be a nonempty table")
            cfg.types = {}
            for name, spec in data["types"].items():
                if not re.fullmatch("[A-Z][A-Z_]*", name) or not isinstance(spec, dict):
                    fail("Invalid type name or table")
                if set(spec) - {"prefix", "allowed_statuses", "require_anchor", "description"}:
                    fail("Unknown type configuration field")
                statuses = spec.get("allowed_statuses")
                if (not isinstance(statuses, list) or not statuses
                    or not all(isinstance(s, str) and re.fullmatch("[A-Z][A-Z_]*", s) for s in statuses)
                    or len(set(statuses)) != len(statuses)):
                    fail("allowed_statuses must be distinct uppercase names")
                if spec.get("prefix", name) != name or type(spec.get("require_anchor", True)) is not bool:
                    fail("prefix must equal type name; require_anchor must be boolean")
                cfg.types[name] = EntityTypeConfig(name, statuses, spec.get("require_anchor", True), spec.get("description", ""))
        return cfg

def find_config_file(start_dir=None):
    current = (start_dir or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / "ledger.toml"
        if candidate.is_file():
            return candidate
        if (directory / ".git").exists():
            break
    return None

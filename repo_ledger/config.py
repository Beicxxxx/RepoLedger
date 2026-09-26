"""Strict Python 3.11+ TOML configuration."""
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import re
import tomllib
from .errors import LedgerError

DEFAULT_GUARD_SCOPE = [
    "*.py", "**/*.py", "*.ts", "**/*.ts", "*.js", "**/*.js",
    "*.go", "**/*.go", "*.rs", "**/*.rs", "*.json", "**/*.json",
    "*.md", "**/*.md",
]

REFERENCE_TOKEN_RE = re.compile(r"[A-Z][A-Z_]*-[0-9]{1,}")


def relative_path(value):
    return (isinstance(value, str) and bool(value) and "\\" not in value
            and ":" not in value and not PurePosixPath(value).is_absolute()
            and all(p not in ("", ".", "..", ".git") for p in value.split("/")))


def _guard_glob(value):
    """Accept repository-relative matching patterns, never arbitrary regex."""
    return (isinstance(value, str) and bool(value) and "\\" not in value
            and ":" not in value and not PurePosixPath(value).is_absolute()
            and all(p not in ("", ".", "..", ".git") for p in value.split("/")))


def _guard_token(value):
    return (isinstance(value, str) and bool(value) and value == value.strip()
            and not any(ord(c) < 32 or c in "\x7f\x85\u2028\u2029" for c in value))


def _reference_token(value):
    """Exemptions name the exact token they silence; never a shape or a path."""
    return isinstance(value, str) and bool(REFERENCE_TOKEN_RE.fullmatch(value))

@dataclass
class EntityTypeConfig:
    prefix: str
    allowed_statuses: list[str]
    require_anchor: bool = True
    description: str = ""


@dataclass
class LegacyGuardConfig:
    enabled: bool = True
    scope_globs: list[str] = field(default_factory=lambda: list(DEFAULT_GUARD_SCOPE))
    exclude_globs: list[str] = field(default_factory=list)
    forbidden_tokens: list[str] = field(default_factory=list)
    file_exemptions: list[str] = field(default_factory=list)
    column_masks: dict[str, list[int]] = field(default_factory=dict)
    fence_exemptions: list[str] = field(default_factory=list)
    string_line_exemptions: dict[str, list[int]] = field(default_factory=dict)


@dataclass
class IndexConfig:
    """Optional [index] table: where repo-ledger index writes pages and whether check verifies them."""
    out_dir: str = ""
    check: bool = False


@dataclass
class FullNameGuardConfig:
    """User-facing prose: every entity mention carries its full registered name."""
    enabled: bool = False
    scope_globs: list[str] = field(default_factory=list)
    exclude_globs: list[str] = field(default_factory=list)
    display_prefixes: dict[str, str] = field(default_factory=dict)


@dataclass
class LetterLabelGuardConfig:
    """Prose ordinals (sections, headings, list and table labels) carry digits only."""
    enabled: bool = False
    scope_globs: list[str] = field(default_factory=lambda: ["*.md", "**/*.md"])
    exclude_globs: list[str] = field(default_factory=list)


@dataclass
class NamingBaselineConfig:
    """Ratchet for historical text: rows may only be removed, never added."""
    path: str = ""
    history_globs: list[str] = field(default_factory=list)
    live_globs: list[str] = field(default_factory=list)


@dataclass
class LedgerConfig:
    schema_version: str = "1.0"
    registry_path: str = ".ledger/ENTITY_REGISTRY.md"
    allow_gaps: bool = True
    independent_order: bool = False
    unique_order_within_scope: bool = False
    code_extensions: list[str] = field(default_factory=lambda: [".py", ".ts", ".js", ".go", ".rs", ".json", ".md"])
    ignore_globs: list[str] = field(default_factory=list)
    reference_exemptions: dict[str, list[str]] = field(default_factory=dict)
    legacy_guard: LegacyGuardConfig = field(default_factory=LegacyGuardConfig)
    index: IndexConfig = field(default_factory=IndexConfig)
    full_name_guard: FullNameGuardConfig = field(default_factory=FullNameGuardConfig)
    letter_label_guard: LetterLabelGuardConfig = field(default_factory=LetterLabelGuardConfig)
    naming_baseline: NamingBaselineConfig = field(default_factory=NamingBaselineConfig)
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
        if set(data) - {"ledger", "types", "legacy_guard", "reference_exemptions", "index",
                        "full_name_guard", "letter_label_guard", "naming_baseline"}:
            fail("Unknown top-level configuration field")
        cfg = cls.default()
        section = data.get("ledger", {})
        allowed = {"schema_version", "registry_path", "allow_gaps", "independent_order",
                   "unique_order_within_scope",
                   "code_extensions", "ignore_globs", "doc_dirs"}
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
        for key in ("allow_gaps", "independent_order", "unique_order_within_scope"):
            if type(getattr(cfg, key)) is not bool:
                fail(f"{key} must be boolean")
        for key in ("code_extensions", "ignore_globs"):
            value = getattr(cfg, key)
            if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
                fail(f"{key} must be a string array")
        if not all(x.startswith(".") for x in cfg.code_extensions):
            fail("code_extensions entries must start with a dot")
        guard_data = data.get("legacy_guard", {})
        if not isinstance(guard_data, dict):
            fail("legacy_guard must be a table")
        allowed_guard = {"enabled", "scope_globs", "exclude_globs", "forbidden_tokens",
                         "file_exemptions", "column_masks", "fence_exemptions",
                         "string_line_exemptions"}
        if set(guard_data) - allowed_guard:
            fail("Unknown legacy_guard field")
        guard = LegacyGuardConfig()
        for key, value in guard_data.items():
            setattr(guard, key, value)
        if type(guard.enabled) is not bool:
            fail("legacy_guard.enabled must be boolean")
        for key in ("scope_globs", "exclude_globs", "file_exemptions"):
            value = getattr(guard, key)
            if not isinstance(value, list) or not all(_guard_glob(x) for x in value):
                fail(f"legacy_guard.{key} must be a string array of safe globs")
        if not isinstance(guard.forbidden_tokens, list) or not all(_guard_token(x) for x in guard.forbidden_tokens):
            fail("legacy_guard.forbidden_tokens must be a string array of literal tokens")
        if len(set(guard.forbidden_tokens)) != len(guard.forbidden_tokens):
            fail("legacy_guard.forbidden_tokens must be distinct")
        if not isinstance(guard.fence_exemptions, list) or not all(isinstance(x, str) for x in guard.fence_exemptions):
            fail("legacy_guard.fence_exemptions must be a string array")
        for key in ("column_masks", "string_line_exemptions"):
            value = getattr(guard, key)
            if not isinstance(value, dict) or not all(
                _guard_glob(path) and isinstance(columns, list)
                and all(type(number) is int and number > 0 for number in columns)
                and len(set(columns)) == len(columns)
                for path, columns in value.items()):
                fail(f"legacy_guard.{key} must map safe globs to distinct positive integer arrays")
        cfg.legacy_guard = guard
        exemptions = data.get("reference_exemptions", {})
        if not isinstance(exemptions, dict) or not all(
            _guard_glob(path) and isinstance(tokens, list) and tokens
            and all(_reference_token(token) for token in tokens)
            and len(set(tokens)) == len(tokens)
            for path, tokens in exemptions.items()):
            fail("reference_exemptions must map safe file globs to distinct TYPE-N literal tokens")
        cfg.reference_exemptions = {path: list(tokens) for path, tokens in exemptions.items()}
        index_data = data.get("index", {})
        if not isinstance(index_data, dict):
            fail("index must be a table")
        if set(index_data) - {"out_dir", "check"}:
            fail("index has an unknown field; only out_dir and check are supported")
        index = IndexConfig(index_data.get("out_dir", ""), index_data.get("check", False))
        if "out_dir" in index_data and not relative_path(index.out_dir):
            fail("index.out_dir must be a safe repository-relative directory without a trailing slash")
        if type(index.check) is not bool:
            fail("index.check must be boolean")
        if index.check and not index.out_dir:
            fail("index.check = true requires index.out_dir")
        cfg.index = index
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
        _load_naming_guards(cfg, data, fail)
        return cfg


def _load_naming_guards(cfg, data, fail):
    """Parse the opt-in naming guards after the type vocabulary is known."""
    def table(name, allowed):
        value = data.get(name, {})
        if not isinstance(value, dict):
            fail(f"{name} must be a table")
        if set(value) - allowed:
            fail(f"Unknown {name} field")
        return value

    def globs(section, key, value):
        if not isinstance(value, list) or not all(_guard_glob(x) for x in value):
            fail(f"{section}.{key} must be a string array of safe globs")
        return list(value)

    section = table("full_name_guard", {"enabled", "scope_globs", "exclude_globs", "display_prefixes"})
    guard = FullNameGuardConfig()
    for key, value in section.items():
        if key == "enabled":
            if type(value) is not bool:
                fail("full_name_guard.enabled must be boolean")
            guard.enabled = value
        elif key == "display_prefixes":
            # Display spellings such as 任务-N map to exactly one configured type.
            if not isinstance(value, dict) or not all(
                    isinstance(prefix, str) and prefix and prefix == prefix.strip()
                    and not any(ch.isspace() or ch in "-|" for ch in prefix)
                    and prefix not in cfg.types
                    and isinstance(target, str) and target in cfg.types
                    for prefix, target in value.items()):
                fail("full_name_guard.display_prefixes must map distinct non-type prefixes "
                     "to configured types")
            guard.display_prefixes = dict(value)
        else:
            setattr(guard, key, globs("full_name_guard", key, value))
    cfg.full_name_guard = guard

    section = table("letter_label_guard", {"enabled", "scope_globs", "exclude_globs"})
    labels = LetterLabelGuardConfig()
    for key, value in section.items():
        if key == "enabled":
            if type(value) is not bool:
                fail("letter_label_guard.enabled must be boolean")
            labels.enabled = value
        else:
            setattr(labels, key, globs("letter_label_guard", key, value))
    cfg.letter_label_guard = labels

    section = table("naming_baseline", {"path", "history_globs", "live_globs"})
    baseline = NamingBaselineConfig()
    for key, value in section.items():
        if key == "path":
            if not isinstance(value, str) or (value and not relative_path(value)):
                fail("naming_baseline.path must be empty or a safe repository-relative file")
            baseline.path = value
        else:
            setattr(baseline, key, globs("naming_baseline", key, value))
    cfg.naming_baseline = baseline

def find_config_file(start_dir=None):
    current = (start_dir or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / "ledger.toml"
        if candidate.is_file():
            return candidate
        if (directory / ".git").exists():
            break
    return None

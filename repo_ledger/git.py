"""Git inventory for the working-tree-only first release."""
from pathlib import Path
import subprocess
from .config import relative_path
from .errors import LedgerError

def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise LedgerError("ERR_GIT", result.stderr.decode("utf-8", "replace").strip(),
                          f"{root}:1:1", category="incomplete")
    return result.stdout.decode("utf-8")

def repository_root(root):
    actual = Path(git(root, "rev-parse", "--show-toplevel").strip()).resolve()
    if root.resolve() != actual:
        raise LedgerError("ERR_REPOSITORY_ROOT", "ledger.toml must be at the Git repository root")
    return actual

def safe_file(root, rel):
    path = root / rel
    if (not relative_path(rel) or not path.resolve().is_relative_to(root.resolve())
        or any(p.is_symlink() for p in (path, *path.parents) if p != root and p.is_relative_to(root))):
        raise LedgerError("ERR_UNSAFE_PATH", f"Unsafe path: {rel}", f"{rel}:1:1")
    return path

def inventory(root):
    stages = git(root, "ls-files", "--stage", "-z").split("\0")
    tracked = set()
    for entry in filter(None, stages):
        meta, path = entry.split("\t", 1)
        mode, _, stage = meta.split()
        if stage != "0":
            raise LedgerError("ERR_MERGE_CONFLICT", "Unmerged index entries", f"{path}:1:1")
        if mode == "160000":
            raise LedgerError("ERR_UNSUPPORTED_SUBMODULE", "Submodule scanning is not supported", f"{path}:1:1", category="incomplete")
        tracked.add(path)
    others = set(filter(None, git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")))
    ignored = sorted(filter(None, git(root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z").split("\0")))
    return tracked, others, ignored

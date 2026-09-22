"""Synchronize the packaged RepoLedger Skill into installed harness skill roots."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

SKILL_NAME = "repo-ledger"
REPO_ROOT = Path(__file__).resolve().parents[1]


def harness_roots(home: Path) -> list[Path]:
    """Skill roots of harnesses that were observed on this machine."""
    return [
        home / ".codex" / "skills",
        home / ".agents" / "skills",
        home / ".claude" / "skills",
        home / ".cursor" / "skills",
        home / ".cursor" / "skills-cursor",
        home / ".qoder" / "skills",
    ]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO_ROOT / "skills" / SKILL_NAME)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--check", action="store_true", help="report drift only; never write")
    parser.add_argument("--install", action="store_true",
                        help="also copy into harness roots that exist without the skill")
    args = parser.parse_args(argv)

    source = args.source / "SKILL.md"
    if not source.is_file():
        print(f"packaged skill missing: {source}", file=sys.stderr)
        return 2
    source_digest = digest(source)
    drift = 0
    for root in harness_roots(args.home):
        if not root.is_dir():
            continue
        target = root / SKILL_NAME / "SKILL.md"
        if not target.is_file():
            if not (args.install and not args.check):
                drift += 1
                print(f"missing   {target}  (--install to add)")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            print(f"installed {target}")
            continue
        if digest(target) == source_digest:
            print(f"same      {target}")
            continue
        drift += 1
        if args.check:
            print(f"stale     {target}")
            continue
        shutil.copyfile(source, target)
        state = "synced" if digest(target) == source_digest else "MISMATCH"
        print(f"{state}    {target}")
    return 1 if (args.check and drift) else 0


if __name__ == "__main__":
    sys.exit(main())


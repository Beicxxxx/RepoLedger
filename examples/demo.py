"""Run a local minimal lifecycle in a temporary Git repository."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repo_ledger.cli import main

def run(root, *args, expected=0):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = main([*args, "--root", str(root), "--json"])
    report = json.loads(stream.getvalue())
    if code != expected:
        raise RuntimeError(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="repo-ledger-demo-") as folder:
        root = Path(folder)
        subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
        (root / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "proposal.md"], check=True, capture_output=True)
        run(root, "init")
        row = run(root, "allocate", "TASK", "max|SMD| proposal", "--anchor", "proposal.md")
        run(root, "lookup", row["id"])
        run(root, "check")
        (root / "next.md").write_text("Investigate TASK-999\n", encoding="utf-8")
        run(root, "check", expected=1)

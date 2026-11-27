"""Exercise both ChatGPT-backed roles in a disposable local fixture. Run explicitly."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import mkdtemp

import coordinator as c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-parent", type=Path, help="Keep the private fixture and receipts here.")
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(mkdtemp(prefix="coordinator-live-smoke-", dir=args.fixture_parent)).resolve()
    primary = root / "fixture"
    linked = root / "candidate"
    primary.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", primary, *args], text=True).strip()

    branch = "research/feedback-smoke"
    path = "market-history/research/universal_agent/engine.py"
    module = primary / path
    module.parent.mkdir(parents=True)
    module.write_text("def answer():\n    return 41\n")
    git("init", "-q", "-b", "fixture")
    git("config", "user.name", "Coordinator smoke")
    git("config", "user.email", "coordinator@example.invalid")
    git("add", "--", path)
    git("commit", "-qm", "Synthetic E2E input")
    base = git("rev-parse", "HEAD")
    git("worktree", "add", "-q", "-b", branch, str(linked), base)
    admin = Path(subprocess.check_output(["git", "-C", linked, "rev-parse", "--absolute-git-dir"],
                                         text=True).strip())
    url = "https://github.com/kegor2-design/market-morning-reports/issues/123"
    issue = root / "synthetic-issue.json"
    c.write_record(issue, dict(url=url, state="OPEN", title="Synthetic coordinator regression",
                               body=("Change answer() in engine.py to return the integer 42. Keep its zero-argument "
                                     "signature. Completion requires independent role executions, the pinned "
                                     "acceptance test, a scoped Git diff, the separate signature regression "
                                     "and the coordinator READY_FOR_PR gate.")))
    c.write_record(admin / "agent-development-scope.json",
                   dict(issue_url=url, branch=branch, base=base, allowed_files=[path]))
    test = ["python3", "-IB", "-c", f"import runpy; assert runpy.run_path({path!r})['answer']() == 42; print('answer() == 42')"]
    signature = ["python3", "-IB", "-c",
                 f"import inspect, runpy; f = runpy.run_path({path!r})['answer']; "
                 "assert len(inspect.signature(f).parameters) == 0; print('signature verified')"]
    print(f"Fixture: {root}\nCheckpoint: {admin / 'development-coordinator/feedback-loop.json'}", flush=True)
    cli = Path(c.__file__).resolve()
    return subprocess.call([sys.executable, "-B", cli, "loop", issue, branch, base, "--worktree", linked,
                            "--test-argv", json.dumps(test), "--workflow-check", "separate signature regression",
                            json.dumps(signature), "--max-calls", "6", "--timeout", "360", "--evidence-dir", root], cwd=linked)


if __name__ == "__main__":
    sys.exit(main())

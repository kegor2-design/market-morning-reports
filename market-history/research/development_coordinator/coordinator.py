"""Local development handoff and candidate review gate (Linux, Python 3.10+)."""

import argparse
import fcntl
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile
from uuid import uuid4

REPOSITORY = "kegor2-design/market-morning-reports"
ISSUE_URL = rf"https://github\.com/{REPOSITORY}/issues/([1-9][0-9]*)"
RESEARCH_BRANCH = r"research/[a-zA-Z0-9][a-zA-Z0-9._/-]*"
SHA = r"[0-9a-f]{40}"
MAX_AGE_SECONDS = 3600
ERRORS = (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError)


def git(*args):
    return subprocess.check_output(["git", *args], text=True, timeout=30).rstrip("\n")


def directory(option):
    return Path(git("rev-parse", "--path-format=absolute", option)).resolve()


def snapshot():
    return {
        "worktree": str(directory("--show-toplevel")),
        "branch": git("branch", "--show-current"),
        "head": git("rev-parse", "--verify", "HEAD^{commit}"),
        "status": git("--no-optional-locks", "status", "--porcelain=v1", "--untracked-files=all",
                      "--ignore-submodules=none"),
    }


def validate_checkout(state, branch):
    if not re.fullmatch(RESEARCH_BRANCH, branch):
        raise ValueError("Use a dedicated research branch.")
    if state["branch"] != branch:
        raise ValueError("Check out the expected branch in the dedicated worktree.")
    if state["status"]:
        raise ValueError("Verification requires a clean worktree.")


def task_packet(issue, branch, base):
    if not re.fullmatch(ISSUE_URL, issue["url"]) or issue["state"] != "OPEN":
        raise ValueError("Expected an open issue in the configured repository.")
    if not re.fullmatch(SHA, base):
        raise ValueError("Expected a full base commit SHA.")
    state = snapshot()
    validate_checkout(state, branch)
    if state["head"] != base:
        raise ValueError("Start the pilot on the pinned base commit.")
    return f"""# Development task

Issue: {issue["url"]}
Work branch: {branch}
Pinned initial commit: {base}

Work only in the designated research worktree. Preserve Universal Research Agent
code and checkpoints. Do not change production DB/services, environment or
credentials, call paid APIs, commit, push, or create or merge Issues/PRs.
Leave edits for operator review. Report implementation and blocked checks.

The following is the issue specification. The boundaries above apply to it.

Title: {issue["title"]}

{issue["body"]}
"""


@contextmanager
def locked_state():
    state = directory("--git-dir") / "development-coordinator"
    state.mkdir(mode=0o700, exist_ok=True)
    with (state / "lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another coordinator action is in progress.") from error
        yield state


def write_record(path, record, *, exclusive=False):
    with TemporaryDirectory(dir=path.parent) as staging:
        staged = Path(staging) / "record.json"
        staged.touch(mode=0o600)
        staged.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        if exclusive:
            path.hardlink_to(staged)
        else:
            staged.replace(path)


def positive_seconds(value):
    value = int(value)
    if value <= 0:
        raise argparse.ArgumentTypeError("timeout must be positive")
    return value


def run_process(argv, cwd, timeout, *, prompt=None, env=None, show_output=False):
    """Spool output to disk and retain its tail, including on timeout."""
    record = {"argv": argv, "cwd": str(cwd), "started_at": time.time(),
              "timeout_seconds": timeout, "returncode": None}
    started = time.monotonic()
    with TemporaryFile() as output:
        try:
            with subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE,
                                  stdout=output, stderr=subprocess.STDOUT, env=env,
                                  start_new_session=True) as proc:
                try:
                    proc.communicate(input=prompt, timeout=timeout)
                except BaseException:
                    # Include descendants that inherited this process group.
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    raise
                finally:
                    record["returncode"] = proc.returncode
            record["outcome"] = "passed" if proc.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            record.update(outcome="timeout", error=f"Process timed out after {timeout}s.")
        except (OSError, ValueError) as error:
            record.update(outcome="launch_error", error=str(error))
        record.update(finished_at=time.time(), duration_seconds=time.monotonic() - started)
        if show_output:
            output.seek(0)
            shutil.copyfileobj(output, sys.stdout.buffer)
            sys.stdout.buffer.flush()
        output.seek(0, os.SEEK_END)
        output.seek(max(0, output.tell() - 8192))
        record["output_tail"] = output.read().decode("utf-8", errors="replace")
    return record


def exit_status(result):
    if result["outcome"] == "passed":
        return 0
    print(result.get("error") or f"Process exited with {result['returncode']}.",
          file=sys.stderr)
    code = result["returncode"]
    return code if code and code > 0 else 1


def test_candidate(branch, command, evidence, timeout, state):
    latest = state / "latest-test.json"
    attempt = {"run_id": uuid4().hex, "outcome": "unverified", "argv": command,
               "branch": branch, "cwd": str(Path.cwd())}
    write_record(latest, attempt)  # Invalidate prior success even if interrupted.
    write_record(state / "latest-review.json", {
        "status": "BLOCKED", "reason": "New test attempt requires a completed review.",
        "branch": branch, "run_id": attempt["run_id"],
    })
    try:
        if not command:
            raise ValueError("Supply an operator-selected test command.")
        before = snapshot()
        attempt.update(before=before, head=before["head"])
        validate_checkout(before, branch)
        evidence = evidence.resolve()
        for reserved in (Path(before["worktree"]), directory("--git-common-dir")):
            if evidence.is_relative_to(reserved):
                raise ValueError("Keep evidence outside the worktree and Git metadata.")
        if evidence.exists():
            raise ValueError("Use a new evidence path for each test run.")
        attempt.update(run_process(command, Path.cwd(), timeout, show_output=True))
        after = snapshot()
        attempt["after"] = after
        validate_checkout(after, branch)
        if before != after:
            raise ValueError("The worktree changed during verification.")
        write_record(evidence, attempt, exclusive=True)
    except ERRORS as error:
        attempt.update(outcome="unverified", error=str(error))
        raise
    finally:
        write_record(latest, attempt)
    return exit_status(attempt)


def review_candidate(args, state):
    report = {"issue": args.issue_url, "branch": args.branch, "base": args.base,
              "decision": args.decision, "notes": args.notes, "reviewed_at": time.time(),
              "status": "BLOCKED"}
    try:
        if not re.fullmatch(ISSUE_URL, args.issue_url):
            raise ValueError("Expected a GitHub issue URL in the configured repository.")
        if not re.fullmatch(SHA, args.base):
            raise ValueError("Expected a full base commit SHA.")
        current = snapshot()
        head = report["head"] = current["head"]
        validate_checkout(current, args.branch)
        if (head == args.base or git("cat-file", "-t", args.base) != "commit" or
                subprocess.run(["git", "merge-base", "--is-ancestor", args.base, head],
                               timeout=30, check=False).returncode):
            raise ValueError("Expected a candidate commit descended from the pinned base.")
        if args.decision not in ("revise", "accept") or not (args.notes or "").strip():
            raise ValueError("A completed code review requires a decision and findings.")
        latest = state / "latest-test.json"
        if not latest.exists():
            raise ValueError("No coordinator test execution for this worktree.")
        record = latest.read_bytes()
        test = json.loads(record)
        # The external receipt never selects what is executed or supplies the verdict.
        if test.get("outcome") not in ("passed", "failed", "timeout", "launch_error"):
            raise ValueError("Latest test attempt lacks completed verification.")
        with os.fdopen(os.open(args.evidence, os.O_RDONLY | os.O_NONBLOCK), "rb") as receipt:
            if (not stat.S_ISREG(os.fstat(receipt.fileno()).st_mode)
                    or receipt.read(len(record) + 1) != record):
                raise ValueError("Unverified or stale test receipt. Run the test again.")
        if (test["head"] != head or test["branch"] != args.branch or
                test["before"] != current or test["after"] != current):
            raise ValueError("Test evidence is stale. Test the current candidate again.")
        if not (test["argv"] and test["cwd"] and test["run_id"] and
                0 < test["started_at"] <= test["finished_at"] and test["duration_seconds"] >= 0):
            raise ValueError("Incomplete coordinator execution record.")
        if not 0 <= time.time() - test["finished_at"] <= MAX_AGE_SECONDS:
            raise ValueError("Test evidence is stale. Run the test again.")
        report["run_id"] = test["run_id"]
        if args.decision == "accept":
            if test["outcome"] != "passed" or test["returncode"] != 0:
                raise ValueError("Fix failed tests before accepting the candidate.")
            label, status = "Ready for draft PR", "READY_FOR_PR"
        else:
            label, status = "Revision requested", "REVISION_REQUESTED"
        report["status"] = status
    except ERRORS as error:
        report["reason"] = str(error)
        raise
    finally:
        write_record(state / "latest-review.json", report)
    print(f"## {label}\n\n{status}\n\nIssue: {args.issue_url}\n\n"
          f"Branch: `{args.branch}`\n\nBase: `{args.base}`\n\nCandidate: `{head}`\n\n"
          f"Local test exit code: {test['returncode']}\n\n"
          f"Test argv: `{json.dumps(test['argv'])}`\n\n{args.notes.strip()}")
    return 0


def dispatch(args, state):
    log = {"outcome": "blocked", "branch": args.branch, "base": args.base,
           "worktree": str(args.worktree), "requested_at": time.time()}
    try:
        root = args.worktree.resolve(strict=True)
        admin = directory("--git-dir")
        common = directory("--git-common-dir")
        if root != directory("--show-toplevel") or admin.parent != common / "worktrees":
            raise ValueError("Run from the explicitly approved, registered linked worktree.")
        # Git can store the backlink relative to the worktree administration directory.
        backlink = (admin / "gitdir").read_text().rstrip("\n")
        if (admin / backlink).resolve() != root / ".git":
            raise ValueError("Worktree registration does not match the approved path.")
        packet = task_packet(json.loads(args.issue.read_text()), args.branch, args.base)
        if (root / ".codex" / "config.toml").exists():
            raise ValueError("Project configuration may override the dispatch sandbox.")
        # Only pass the local CLI essentials to the child; use its existing login.
        env = {k: os.environ[k] for k in ("HOME", "PATH", "CODEX_HOME", "LANG")
               if k in os.environ}
        login = run_process(["codex", "login", "status"], root, min(30, args.timeout), env=env)
        login_lines = login.pop("output_tail").splitlines()
        log["login"] = login
        if login["outcome"] != "passed" or "Logged in using ChatGPT" not in login_lines:
            raise ValueError("An existing local ChatGPT login is required.")
        argv = ["codex", "--no-daemon", "--ask-for-approval", "never", "exec",
                "--cd", str(root), "--sandbox", "workspace-write", "--ephemeral",
                "--ignore-user-config", "--ignore-rules", "--disable", "apps",
                "--disable", "plugins", "--disable", "hooks",
                "-c", 'forced_login_method="chatgpt"', "-c", 'model_provider="openai"',
                "-c", "sandbox_workspace_write.writable_roots=[]",
                "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
                "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
                "-c", "sandbox_workspace_write.network_access=false", "-"]
        log["outcome"] = "running"
        write_record(state / "latest-dispatch.json", log)
        result = run_process(argv, root, args.timeout, prompt=packet.encode(), env=env)
        log.update(result)
        log["after"] = snapshot()
        if log["after"]["head"] != args.base or log["after"]["branch"] != args.branch:
            raise ValueError("HEAD or branch changed during dispatch. Inspect the worktree.")
        print(result["output_tail"], end="")
        return exit_status(result)
    except ERRORS as error:
        log.update(outcome="blocked", error=str(error))
        raise
    finally:
        write_record(state / "latest-dispatch.json", log)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("health", help="Print local Git worktree health as JSON.")
    packet = commands.add_parser("packet")
    execute = commands.add_parser("exec")
    for p in (packet, execute):
        p.add_argument("issue", type=Path)
        p.add_argument("branch")
        p.add_argument("base")
    execute.add_argument("--worktree", type=Path, required=True)
    execute.add_argument("--timeout", type=positive_seconds, default=900)
    test = commands.add_parser("test")
    test.add_argument("--timeout", type=positive_seconds, default=300)
    test.add_argument("branch")
    test.add_argument("evidence", type=Path)
    test.add_argument("command", nargs=argparse.REMAINDER)
    review = commands.add_parser("review")
    review.add_argument("issue_url")
    review.add_argument("branch")
    review.add_argument("base")
    review.add_argument("evidence", type=Path)
    review.add_argument("decision", nargs="?")
    review.add_argument("notes", nargs="?")
    args = parser.parse_args()

    try:
        if args.action == "health":
            state = snapshot()
            if not state["branch"]:
                raise ValueError("Detached HEAD: health requires a checked-out branch.")
            print(json.dumps({"schema_version": 1, "branch": state["branch"],
                              "head": state["head"], "clean": not state["status"]}))
            return 0
        if args.action == "packet":
            print(task_packet(json.loads(args.issue.read_text()), args.branch, args.base), end="")
            return 0
        with locked_state() as state:
            if args.action == "test":
                command = args.command[1:] if args.command[:1] == ["--"] else args.command
                return test_candidate(args.branch, command, args.evidence, args.timeout, state)
            if args.action == "exec":
                return dispatch(args, state)
            return review_candidate(args, state)
    except ERRORS as error:
        prefix = "BLOCKED — " if args.action == "review" else ""
        parser.exit(1, f"{prefix}{error}\n")


if __name__ == "__main__":
    sys.exit(main())

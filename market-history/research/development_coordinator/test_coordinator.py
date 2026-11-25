"""Exercise the Issue-to-revision flow using real Git commits and a local Issue fixture."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("coordinator.py").resolve()
BRANCH = "research/coordinator-pilot"
ISSUE = "https://github.com/kegor2-design/market-morning-reports/issues/123"


class CoordinatorTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", BRANCH)
        self.git("config", "user.name", "Coordinator test")
        self.git("config", "user.email", "coordinator@example.invalid")
        self.git("commit", "--allow-empty", "-m", "Pinned base")
        self.base = self.git("rev-parse", "HEAD")
        self.issue = self.root / "issue.json"
        self.issue.write_text(json.dumps({
            "url": ISSUE,
            "state": "OPEN",
            "title": "Implement a checked answer",
            "body": "The program must print 42.",
        }))

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def cli_result(self, *args, cwd=None, env=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            cwd=cwd or self.repo, capture_output=True, text=True, env=env, timeout=20,
        )

    def cli(self, *args, code=0, env=None):
        result = self.cli_result(*args, env=env)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def commit_answer(self, answer):
        (self.repo / "answer.py").write_text(f"print({answer})\n")
        self.git("add", "answer.py")
        self.git("commit", "-m", f"Answer {answer}")
        return self.git("rev-parse", "HEAD")

    def test_health_reports_clean_checkout_without_writes(self):
        self.git("branch", "-m", "main")
        head = self.commit_answer(42)
        index = self.repo / ".git" / "index"
        before = index.read_bytes()
        # Make the cached file timestamp stale while keeping the contents clean.
        os.utime(self.repo / "answer.py", (1000000000, 1000000000))
        report = json.loads(self.cli("health"))
        self.assertEqual(report, {"schema_version": 1, "branch": "main",
                                  "head": head, "clean": True})
        self.assertIs(type(report["schema_version"]), int)
        self.assertIs(report["clean"], True)
        self.assertEqual(index.read_bytes(), before)
        self.assertFalse((self.repo / ".git" / "development-coordinator").exists())

    def test_health_reports_dirty_worktree_from_subdirectory(self):
        subdir = self.repo / "nested"
        subdir.mkdir()
        self.commit_answer(42)
        def assert_dirty(change):
            with self.subTest(change=change):
                result = self.cli_result("health", cwd=subdir)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIs(json.loads(result.stdout)["clean"], False)

        untracked = self.repo / "new.txt"
        untracked.touch()
        assert_dirty("untracked")
        untracked.unlink()
        (self.repo / "answer.py").write_text("print(41)\n")
        assert_dirty("unstaged")
        self.git("add", "answer.py")
        assert_dirty("staged")

    def test_health_rejects_invalid_git_states(self):
        self.git("checkout", "-q", "--detach")
        unborn = self.root / "unborn"
        self.git("init", "-q", "-b", "main", str(unborn))
        for cwd in (self.repo, unborn, self.root):
            with self.subTest(cwd=cwd):
                result = self.cli_result("health", cwd=cwd)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.strip())
                self.assertNotIn("Traceback", result.stderr)

    def test_issue_revision_and_retest(self):
        packet = self.cli("packet", self.issue, BRANCH, self.base)
        self.assertIn(ISSUE, packet)
        self.assertIn(self.base, packet)
        self.assertIn("The program must print 42.", packet)
        first = self.commit_answer(41)
        command = [
            sys.executable, "-c",
            "import subprocess, sys; sys.exit("
            "subprocess.check_output([sys.executable, 'answer.py']).strip() != b'42')",
        ]
        failed = self.root / "failed.json"
        self.cli("test", BRANCH, failed, "--", *command, code=1)
        self.assertIn("Fix failed tests", self.cli(
            "review", ISSUE, BRANCH, self.base, failed, "accept", "Approved", code=1,
        ))
        revision = self.cli(
            "review", ISSUE, BRANCH, self.base, failed, "revise", "Print 42 rather than 41.",
        )
        self.assertIn("Revision requested", revision)
        self.assertIn(first, revision)
        final = self.commit_answer(42)
        self.assertIn("stale", self.cli(
            "review", ISSUE, BRANCH, self.base, failed, "accept", "Approved", code=1,
        ))
        passed = self.root / "passed.json"
        self.cli("test", BRANCH, passed, "--", *command)
        acceptance = self.cli(
            "review", ISSUE, BRANCH, self.base, passed, "accept", "Confirmed output 42.",
        )
        self.assertIn("Ready for draft PR", acceptance)
        self.assertIn(final, acceptance)

    def test_rejects_wrong_issue_branch_and_dirty_worktree(self):
        issue = json.loads(self.issue.read_text())
        issue["url"] = "https://github.com/other/project/issues/123"
        self.issue.write_text(json.dumps(issue))
        self.assertIn("Expected an open issue", self.cli(
            "packet", self.issue, BRANCH, self.base, code=1,
        ))
        evidence = self.root / "evidence.json"
        self.assertIn("expected branch", self.cli(
            "test", "research/other", evidence, "--", sys.executable, "-V", code=1,
        ))
        (self.repo / "untracked").touch()
        self.assertIn("clean worktree", self.cli(
            "test", BRANCH, evidence, "--", sys.executable, "-V", code=1,
        ))
        self.assertFalse(evidence.exists())

    def test_rejects_test_that_leaves_changes(self):
        evidence = self.root / "evidence.json"
        self.assertIn("clean worktree", self.cli(
            "test", BRANCH, evidence, "--", sys.executable, "-c",
            "from pathlib import Path; Path('new_file').touch()", code=1,
        ))
        self.assertFalse(evidence.exists())


    def record_path(self, name):
        return Path(self.git("rev-parse", "--absolute-git-dir")) / "development-coordinator" / name

    def run_test(self, name, *command, timeout=10, code=0):
        receipt = self.root / name
        self.cli("test", "--timeout", timeout, BRANCH, receipt, "--", *command, code=code)
        return receipt

    def approve(self, receipt, *, code=0, base=None):
        return self.cli("review", ISSUE, BRANCH, base or self.base, receipt,
                        "accept", "Reviewed candidate diff and test scope.", code=code)

    def assert_blocked(self, receipt):
        message = self.approve(receipt, code=1)
        self.assertIn("BLOCKED", message)
        self.assertNotIn("READY_FOR_PR", message)
        review = json.loads(self.record_path("latest-review.json").read_text())
        self.assertEqual(review["status"], "BLOCKED")
        self.assertTrue(review["reason"])

    def test_forged_and_edited_receipts_cannot_approve(self):
        head = self.commit_answer(41)
        receipt = self.root / "fake.json"
        receipt.write_text(json.dumps({"head": head, "branch": BRANCH, "returncode": 0,
                                       "argv": [sys.executable, "-V"]}))
        self.assert_blocked(receipt)
        failed = self.run_test("failed.json", sys.executable, "-c", "exit(7)", code=7)
        record = json.loads(failed.read_text())
        record.update(returncode=0, outcome="passed")
        failed.write_text(json.dumps(record, indent=2) + "\n")
        self.assert_blocked(failed)

    def test_current_execution_and_review_required(self):
        self.commit_answer(42)
        passed = self.run_test("passed.json", sys.executable, "answer.py")
        for review in ([], ["accept"], ["accept", "  "]):
            with self.subTest(review=review):
                self.assertIn("completed code review", self.cli(
                    "review", ISSUE, BRANCH, self.base, passed, *review, code=1))
        self.assert_blocked(self.root / "missing.json")
        fifo = self.root / "receipt.fifo"
        os.mkfifo(fifo)
        self.assert_blocked(fifo)
        current = self.run_test("failed.json", sys.executable, "-c", "exit(1)", code=1)
        self.assert_blocked(passed)
        self.assert_blocked(current)
        retry = self.run_test("retry.json", sys.executable, "answer.py")
        self.assertIn("READY_FOR_PR", self.approve(retry))
        pending = self.root / "skipped.json"
        self.cli("test", BRANCH, pending, code=1)
        self.assert_blocked(retry)

    def test_wrong_candidate_and_base_sha(self):
        head = self.commit_answer(42)
        passed = self.run_test("passed.json", sys.executable, "answer.py")
        blob = self.git("rev-parse", "HEAD:answer.py")
        for base in ("abc", "f" * 40, head, blob):
            with self.subTest(base=base):
                self.assertIn("BLOCKED", self.approve(passed, code=1, base=base))
        self.assertIn("pinned base", self.cli("packet", self.issue, BRANCH, self.base, code=1))
        record = json.loads(passed.read_text())
        record["head"] = self.base
        passed.write_text(json.dumps(record, indent=2) + "\n")
        self.assert_blocked(passed)

    def test_expired_receipt_and_dirty_review(self):
        self.commit_answer(42)
        passed = self.run_test("passed.json", sys.executable, "answer.py")
        (self.repo / "answer.py").write_text("print(41)\n")
        self.assert_blocked(passed)
        self.git("restore", "answer.py")
        # Model a genuine run from two hours ago, including the local journal.
        record = json.loads(passed.read_text())
        record["started_at"] -= 7200
        record["finished_at"] -= 7200
        for path in (passed, self.record_path("latest-test.json")):
            path.write_text(json.dumps(record, indent=2) + "\n")
        self.assertIn("stale", self.approve(passed, code=1))

    def test_execution_metadata_timeout_signal_launch_error_and_retry(self):
        head = self.commit_answer(42)
        commands = [
            ("timeout", [sys.executable, "-c", "import time; time.sleep(30)"], -signal.SIGKILL),
            ("failed", [sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"],
             -signal.SIGTERM),
            ("launch_error", [str(self.root / "absent")], None),
        ]
        for outcome, argv, rc in commands:
            with self.subTest(outcome=outcome):
                receipt = self.run_test(outcome + ".json", *argv, timeout=1, code=1)
                data = json.loads(receipt.read_text())
                self.assertEqual(data["outcome"], outcome)
                self.assertEqual(data["returncode"], rc)
                self.assertEqual(data["argv"], argv)
                self.assertEqual(data["cwd"], str(self.repo))
                self.assertEqual(data["before"], {"head": head, "branch": BRANCH,
                                                  "worktree": str(self.repo), "status": ""})
                self.assertEqual(data["after"], data["before"])
                self.assertGreater(data["duration_seconds"], 0)
                self.assertGreaterEqual(data["finished_at"], data["started_at"])
                self.assert_blocked(receipt)
        retry = self.run_test("retry.json", sys.executable, "answer.py")
        self.assertIn("READY_FOR_PR", self.approve(retry))

    def test_concurrent_attempt_cannot_approve_old_success(self):
        self.commit_answer(42)
        previous = self.run_test("first.json", sys.executable, "answer.py")
        marker = self.root / "started"
        release = self.root / "release"
        program = ("import pathlib,sys,time\npathlib.Path(sys.argv[1]).touch()\n"
                   "while not pathlib.Path(sys.argv[2]).exists(): time.sleep(0.02)\n")
        with subprocess.Popen([sys.executable, str(SCRIPT), "test", "--timeout", "10",
                               BRANCH, str(self.root / "second.json"), "--", sys.executable,
                               "-c", program, str(marker), str(release)], cwd=self.repo) as run:
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(marker.exists())
                self.assertIn("in progress", self.approve(previous, code=1))
            finally:
                release.touch()
            self.assertEqual(run.wait(timeout=5), 0)
        self.assert_blocked(previous)

    def linked_worktree(self):
        linked = self.root / "linked"
        self.git("branch", "-m", "primary")
        self.git("worktree", "add", "-q", "-b", BRANCH, str(linked), self.base)
        self.repo = linked

    def fake_codex(self, body, *, chatgpt=True):
        shim = self.root / "codex"
        login = "Logged in using ChatGPT" if chatgpt else "Logged in using an API key"
        shim.write_text(f"#!{sys.executable}\nimport json, os, sys, time\nfrom pathlib import Path\n"
                        f"if sys.argv[1:] == ['login', 'status']:\n    print({login!r})\n    sys.exit(0)\n"
                        + body)
        shim.chmod(0o700)
        return {**os.environ, "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
                "OPENAI_API_KEY": "test-only"}

    def dispatch(self, env, *, approved=None, timeout=5, code=0):
        return self.cli("exec", self.issue, BRANCH, self.base, "--worktree",
                        approved or self.repo, "--timeout", timeout, code=code, env=env)

    def test_dispatch_requires_linked_approved_clean_tree_and_chatgpt(self):
        env = self.fake_codex("Path('dispatched').touch()\n", chatgpt=False)
        self.assertIn("linked worktree", self.dispatch(env, code=1))
        primary = self.repo
        self.linked_worktree()
        self.assertIn("linked worktree", self.dispatch(env, approved=primary, code=1))
        self.assertIn("ChatGPT login", self.dispatch(env, code=1))
        (self.repo / "dirty").touch()
        self.assertIn("clean worktree", self.dispatch(env, code=1))
        self.assertFalse((self.repo / "dispatched").exists())

    def test_dispatch_uses_stdin_and_pinned_sandbox_options(self):
        self.linked_worktree()
        marker = self.root / "should-not-exist"
        issue = json.loads(self.issue.read_text())
        issue["body"] = f"--add-dir /; $(touch {marker})"
        self.issue.write_text(json.dumps(issue))
        env = self.fake_codex(
            "Path('edit.json').write_text(json.dumps([sys.argv[1:], sys.stdin.read(),"
            "os.getcwd(), 'OPENAI_API_KEY' in os.environ]))\n")
        self.dispatch(env)
        argv, packet, cwd, has_api_key = json.loads((self.repo / "edit.json").read_text())
        self.assertIn("exec", argv)
        for option, value in (("--cd", str(self.repo)), ("--ask-for-approval", "never"),
                              ("--sandbox", "workspace-write")):
            self.assertEqual(argv[argv.index(option) + 1], value)
        self.assertEqual(argv[-1], "-")
        self.assertNotIn("--add-dir", argv)
        self.assertNotIn(issue["body"], argv)
        self.assertIn(issue["body"], packet)
        self.assertFalse(marker.exists())
        self.assertEqual(cwd, str(self.repo))
        self.assertFalse(has_api_key)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_dispatch_timeout_error_and_retry(self):
        self.linked_worktree()
        for outcome, body, code in (("timeout", "time.sleep(30)", 1),
                                    ("failed", "print('offline', file=sys.stderr); sys.exit(9)", 9),
                                    ("passed", "print('completed')", 0)):
            with self.subTest(outcome=outcome):
                env = self.fake_codex(body)
                self.dispatch(env, timeout=1, code=code)
                record = json.loads(self.record_path("latest-dispatch.json").read_text())
                self.assertEqual(record["outcome"], outcome)
                if outcome == "failed":
                    self.assertIn("offline", record["output_tail"])


if __name__ == "__main__":
    unittest.main()

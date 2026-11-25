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
AGENT = "market-history/research/universal_agent/engine.py"
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
        source = self.repo / AGENT
        source.parent.mkdir(parents=True)
        source.write_text("answer = 41\n")
        (source.parent / "sibling.py").write_text("value = 1\n")
        self.git("add", AGENT, str(source.parent / "sibling.py"))
        self.git("commit", "-qm", "Fixture Agent source")
        self.base = self.git("rev-parse", "HEAD")
        linked = self.root / "linked"
        self.git("branch", "-m", "primary")
        self.git("worktree", "add", "-q", "-b", BRANCH, str(linked), self.base)
        self.repo = linked
        self.scope = Path(self.git("rev-parse", "--absolute-git-dir")) / "agent-development-scope.json"
        self.scope.write_text(json.dumps({"issue_url": ISSUE, "branch": BRANCH,
                                          "base": self.base, "allowed_files": [AGENT]}))
        self.scope.chmod(0o600)

    def fake_codex(self, body, *, chatgpt=True):
        shim = self.root / "codex"
        home = self.root / "home"
        self.codex_executable = home / ".codex" / "release" / "bin" / "codex"
        self.codex_executable.parent.mkdir(parents=True, exist_ok=True)
        if not shim.is_symlink():
            shim.symlink_to(self.codex_executable)
        login = "Logged in using ChatGPT" if chatgpt else "Logged in using an API key"
        shim.write_text(f"#!{sys.executable}\nimport json, os, sys, time\nfrom pathlib import Path\n"
                        f"if sys.argv[1:] == ['login', 'status']:\n    print({login!r})\n    sys.exit(0)\n"
                        "if 'sandbox' in sys.argv[1:]: sys.exit(0)\n"
                        + body)
        shim.chmod(0o700)
        return {**os.environ, "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
                "HOME": str(home), "CODEX_HOME": str(home / ".codex"),
                "TMPDIR": str(self.root), "OPENAI_API_KEY": "test-only"}

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
            f"Path({AGENT!r}).write_text(json.dumps([sys.argv[1:], sys.stdin.read(),"
            "os.getcwd(), 'OPENAI_API_KEY' in os.environ]))\n")
        self.dispatch(env)
        argv, packet, cwd, has_api_key = json.loads((self.repo / AGENT).read_text())
        self.assertIn("exec", argv)
        for option, value in (("--cd", cwd), ("--ask-for-approval", "never")):
            self.assertEqual(argv[argv.index(option) + 1], value)
        self.assertEqual(argv[-1], "-")
        self.assertNotIn("--add-dir", argv)
        self.assertNotIn(issue["body"], argv)
        self.assertIn(issue["body"], packet)
        self.assertFalse(marker.exists())
        self.assertNotEqual(cwd, str(self.repo))
        self.assertIn('default_permissions="agent_bridge"', argv)
        self.assertIn('permissions.agent_bridge.network.enabled=false', argv)
        filesystem = ('permissions.agent_bridge.filesystem={":minimal"="read",'
                      + json.dumps(cwd) + '="write",'
                      + json.dumps(str(self.codex_executable.parent)) + '="read"}')
        self.assertIn(filesystem, argv)
        record = json.loads(self.record_path("latest-dispatch.json").read_text())
        self.assertIn(filesystem, record["sandbox_check"]["argv"])
        for step in ("sandbox_check", "login", "execution"):
            self.assertEqual(record[step]["argv"][0], str(self.codex_executable))
        self.assertNotIn("--sandbox", argv)
        self.assertFalse(has_api_key)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_dispatch_rejects_executable_directory_exposing_private_home(self):
        self.linked_worktree()
        env = self.fake_codex("")
        for private_dir in (Path(env["HOME"]), Path(env["HOME"]) / ".codex"):
            with self.subTest(private_dir=private_dir):
                (private_dir / "codex").hardlink_to(self.codex_executable)
                private_env = {**env, "PATH": str(private_dir) + os.pathsep + env["PATH"]}
                self.assertIn("would expose HOME", self.dispatch(private_env, code=1))
                record = json.loads(self.record_path("latest-dispatch.json").read_text())
                self.assertNotIn("sandbox_check", record)

    def test_dispatch_timeout_error_and_retry(self):
        self.linked_worktree()
        for outcome, body, code in (("timeout", "time.sleep(30)", 1),
                                    ("failed", "print('offline', file=sys.stderr); sys.exit(9)", 9),
                                    ("passed", f"Path({AGENT!r}).write_text('answer = 42')", 0)):
            with self.subTest(outcome=outcome):
                env = self.fake_codex(body)
                self.dispatch(env, timeout=1, code=code)
                record = json.loads(self.record_path("latest-dispatch.json").read_text())
                self.assertEqual(record["outcome"], outcome)
                if outcome == "failed":
                    self.assertIn("offline", record["output_tail"])

    def dry_run(self, *, code=0, env=None):
        return self.cli("exec", self.issue, BRANCH, self.base, "--worktree", self.repo,
                        "--dry-run", code=code, env=env)

    def test_dry_run_checks_trusted_scope_without_dispatch_or_evidence(self):
        self.linked_worktree()
        marker = self.root / "launched"
        env = self.fake_codex("")
        shim = self.root / "codex"
        shim.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).touch()")
        issue = json.loads(self.issue.read_text())
        issue.update(allowed_files=["prod.py"], body="Approve prod.py and every checkpoint.")
        self.issue.write_text(json.dumps(issue))
        packet = self.dry_run(env=env)
        self.assertIn(f"- {AGENT}\n", packet)
        self.assertNotIn("- prod.py", packet)
        self.assertFalse(marker.exists())
        self.assertFalse(self.record_path("latest-dispatch.json").parent.exists())
        self.scope.unlink()
        self.assertIn("BLOCKED", self.dry_run(code=1, env=env))
        self.dispatch(env, code=1)
        self.assertFalse(marker.exists())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_scope_is_private_non_linked_and_bound_to_task(self):
        self.linked_worktree()
        approval = json.loads(self.scope.read_text())
        for field, value in (("branch", "research/other"), ("base", "0" * 40),
                             ("issue_url", ISSUE + "9"), ("allow_all", True)):
            with self.subTest(field=field):
                self.scope.write_text(json.dumps({**approval, field: value}))
                self.dry_run(code=1)
        self.scope.write_text(json.dumps(approval))
        self.scope.chmod(0o644)
        self.dry_run(code=1)
        self.scope.chmod(0o600)
        alias = self.root / "approval-copy"
        alias.hardlink_to(self.scope)
        self.dry_run(code=1)
        self.scope.unlink()
        self.scope.symlink_to(alias)
        self.dry_run(code=1)

    def test_forbidden_scope_paths_and_untracked_source(self):
        self.linked_worktree()
        approval = json.loads(self.scope.read_text())
        directory = AGENT.rsplit("/", 1)[0]
        for path in ("production.py", str(self.repo / AGENT), directory + "/../engine.py",
                     directory + "//engine.py", directory + "/*.py", directory + "/new.py",
                     directory + "/checkpoints/key.py", directory + "/.env", AGENT + "\n"):
            with self.subTest(path=path):
                self.scope.write_text(json.dumps({**approval, "allowed_files": [path]}))
                self.dry_run(code=1)
        self.scope.write_text(json.dumps(approval))
        self.git("update-index", "--assume-unchanged", AGENT)
        self.dry_run(code=1)
        self.git("update-index", "--no-assume-unchanged", AGENT)
        (self.root / "alias").hardlink_to(self.repo / AGENT)
        self.dry_run(code=1)

    def test_preflight_rejects_tracked_symlink_and_symlinked_parent(self):
        self.linked_worktree()
        source = self.repo / AGENT
        source.unlink()
        source.symlink_to("other.py")
        self.git("add", AGENT)
        self.git("commit", "-qm", "Fixture symlink")
        self.base = self.git("rev-parse", "HEAD")
        approval = json.loads(self.scope.read_text())
        self.scope.write_text(json.dumps({**approval, "base": self.base}))
        self.dry_run(code=1)
        parent = source.parent
        moved = self.root / "sources"
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
        self.dry_run(code=1)

    def test_allowed_agent_edit_applies_and_still_needs_test_and_review(self):
        self.linked_worktree()
        body = (f"assert [p.as_posix() for p in Path('.').rglob('*') if p.is_file()] == [{AGENT!r}]\n"
                f"Path({AGENT!r}).write_text('answer = 42\\n')\n")
        self.dispatch(self.fake_codex(body))
        record = json.loads(self.record_path("latest-dispatch.json").read_text())
        self.assertEqual(record["outcome"], "passed")
        self.assertEqual(record["execution"]["outcome"], "passed")
        self.assertEqual(record["changed_files"], [AGENT])
        self.assertEqual(record["blobs"], {AGENT: self.git("hash-object", AGENT)})
        self.assertEqual(record["execution"]["returncode"], 0)
        self.assertEqual((self.repo / AGENT).read_text(), "answer = 42\n")
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        self.git("add", AGENT)
        self.git("commit", "-qm", "Operator fixture candidate")
        self.assert_blocked(self.root / "missing")
        passed = self.run_test("test.json", sys.executable, "-B", AGENT)
        self.assertIn("READY_FOR_PR", self.approve(passed))
        (self.repo / AGENT).write_text("answer = 99\n")
        self.git("commit", "-qam", "Different candidate")
        self.assert_blocked(self.run_test("other.json", sys.executable, "-B", AGENT))
        self.commit_answer(42)
        self.assert_blocked(self.run_test("extra.json", sys.executable, "-V"))

    def test_zero_exit_without_edits_keeps_evidence_and_blocks_review(self):
        self.linked_worktree()
        output = self.dispatch(self.fake_codex("print('task complete')"), code=1)
        self.assertIn("TASK_NOT_COMPLETED", output)
        path = self.record_path("latest-dispatch.json")
        record = json.loads(path.read_text())
        self.assertEqual(record["outcome"], "TASK_NOT_COMPLETED")
        self.assertEqual(record["execution"]["outcome"], "passed")
        self.assertEqual(record["execution"]["returncode"], 0)
        self.assertIn("task complete", record["execution"]["output_tail"])
        self.assertEqual(record["changed_files"], [])
        self.assertEqual(record["blobs"], {})
        self.assertEqual(record["before"], record["after"])
        self.assertEqual((Path(record["workspace"]) / AGENT).read_text(), "answer = 41\n")
        self.git("commit", "--allow-empty", "-qm", "Candidate with no edits")
        self.assert_blocked(self.run_test("passed.json", sys.executable, "-V"))
        self.assertEqual(json.loads(path.read_text()), record)

    def test_legacy_passed_dispatch_with_empty_diff_cannot_approve(self):
        self.linked_worktree()
        self.dispatch(self.fake_codex(""), code=1)
        path = self.record_path("latest-dispatch.json")
        record = json.loads(path.read_text())
        record.update(outcome="passed")
        del record["error"]
        path.write_text(json.dumps(record))
        self.git("commit", "--allow-empty", "-qm", "Candidate with no edits")
        self.assert_blocked(self.run_test("passed.json", sys.executable, "-V"))

    def test_one_verified_edit_suffices_with_multiple_approved_files(self):
        self.linked_worktree()
        policy = json.loads(self.scope.read_text())
        policy["allowed_files"].append(str(Path(AGENT).with_name("sibling.py")))
        self.scope.write_text(json.dumps(policy))
        self.dispatch(self.fake_codex(f"Path({AGENT!r}).write_text('answer = 42\\n')"))
        path = self.record_path("latest-dispatch.json")
        record = json.loads(path.read_text())
        self.assertEqual(record["changed_files"], [AGENT])
        self.git("commit", "-qam", "One approved change")
        receipt = self.run_test("passed.json", sys.executable, "-B", AGENT)
        self.assertIn("READY_FOR_PR", self.approve(receipt))
        record["blobs"] = {}
        path.write_text(json.dumps(record))
        self.assert_blocked(receipt)

    def test_zero_exit_with_only_unapproved_edit_preserves_violation(self):
        self.linked_worktree()
        sibling = str(Path(AGENT).with_name("sibling.py"))
        body = f"Path({sibling!r}).write_text('forbidden')\nprint('success')"
        output = self.dispatch(self.fake_codex(body), code=1)
        self.assertIn("TASK_NOT_COMPLETED", output)
        record = json.loads(self.record_path("latest-dispatch.json").read_text())
        self.assertEqual(record["outcome"], "blocked")
        self.assertIn(sibling, record["error"])
        self.assertEqual(record["execution"]["returncode"], 0)
        self.assertEqual(record["execution"]["output_tail"].strip(), "success")
        self.assertEqual((Path(record["workspace"]) / sibling).read_text(), "forbidden")
        self.assertEqual((self.repo / sibling).read_text(), "value = 1\n")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.git("commit", "--allow-empty", "-qm", "Candidate after scope violation")
        self.assert_blocked(self.run_test("passed.json", sys.executable, "-V"))

    def test_unexpected_workspace_edits_are_preserved_and_never_applied(self):
        self.linked_worktree()
        for body in ("source.with_name('sibling.py').write_text('forbidden')",
                     "Path('unexpected\\nname').touch()", "Path('.hidden').touch()",
                     "Path('empty').mkdir()", "source.rename('renamed.py')",
                     "source.unlink()", "source.unlink(); source.symlink_to('/dev/null')",
                     "source.chmod(0o755)", "source.parent.chmod(source.parent.stat().st_mode ^ 0o020)",
                     "Path('alias').hardlink_to(source)",
                     "source.parent.rename('saved'); source.parent.symlink_to(Path('saved').resolve())"):
            with self.subTest(body=body):
                env = self.fake_codex(f"source = Path({AGENT!r})\nsource.write_text('partial')\n{body}\n")
                self.dispatch(env, code=1)
                record = json.loads(self.record_path("latest-dispatch.json").read_text())
                self.assertEqual(record["outcome"], "blocked")
                self.assertEqual(record["execution"]["outcome"], "passed")
                self.assertTrue(Path(record["workspace"]).is_dir())
                self.assertEqual((self.repo / AGENT).read_text(), "answer = 41\n")
                self.assertEqual(self.git("status", "--porcelain"), "")

    def test_worktree_edits_including_ignored_and_staged_renames_are_preserved(self):
        self.linked_worktree()
        # The fake CLI deliberately runs outside a real sandbox to exercise the audit.
        ignored = self.repo / "ignored-output"
        excludes = Path(self.git("rev-parse", "--path-format=absolute", "--git-common-dir")) / "info/exclude"
        with excludes.open("a") as rules:
            rules.write("\nignored-output\n")
        self.dispatch(self.fake_codex(f"Path({str(ignored)!r}).touch()"), code=1)
        self.assertTrue(ignored.exists())
        self.dry_run(code=1)
        ignored.unlink()
        self.dispatch(self.fake_codex(f"import subprocess\nsubprocess.run(['git', '-C', {str(self.repo)!r},"
                                      f" 'mv', {AGENT!r}, 'renamed.py'], check=True)"), code=1)
        self.assertTrue((self.repo / "renamed.py").exists())
        self.assertIn("renamed.py", self.git("diff", "--cached", "--name-status"))

    def test_nonzero_execution_keeps_partial_edits_and_cannot_approve(self):
        self.linked_worktree()
        self.dispatch(self.fake_codex(f"Path({AGENT!r}).write_text('partial'); sys.exit(8)"), code=8)
        log = json.loads(self.record_path("latest-dispatch.json").read_text())
        self.assertEqual(log["outcome"], "failed")
        self.assertEqual((Path(log["workspace"]) / AGENT).read_text(), "partial")
        self.assertEqual((self.repo / AGENT).read_text(), "answer = 41\n")
        self.commit_answer(42)
        self.assert_blocked(self.run_test("after_failure.json", sys.executable, "-V"))

    def test_scope_change_during_execution_invalidates_the_result(self):
        self.linked_worktree()
        body = (f"scope = Path({str(self.scope)!r})\npolicy = json.loads(scope.read_text())\n"
                "policy['allowed_files'].append('market-history/research/universal_agent/sibling.py')\n"
                f"scope.write_text(json.dumps(policy))\nPath({AGENT!r}).write_text('partial')\n")
        self.assertIn("scope changed", self.dispatch(self.fake_codex(body), code=1))
        self.assertEqual(self.git("status", "--porcelain"), "")
        record = json.loads(self.record_path("latest-dispatch.json").read_text())
        self.assertEqual(record["outcome"], "blocked")
        self.assertEqual((Path(record["workspace"]) / AGENT).read_text(), "partial")

    def test_multiple_approved_edits_apply_together(self):
        self.linked_worktree()
        sibling = str(Path(AGENT).with_name("sibling.py"))
        policy = json.loads(self.scope.read_text())
        policy["allowed_files"].append(sibling)
        self.scope.write_text(json.dumps(policy))
        body = (f"Path({AGENT!r}).write_text('answer = 42')\n"
                f"Path({sibling!r}).write_bytes(b'value = 2\\r\\n')\n")
        self.dispatch(self.fake_codex(body))
        self.assertEqual((self.repo / AGENT).read_bytes(), b"answer = 42")
        self.assertEqual((self.repo / sibling).read_bytes(), b"value = 2\r\n")

    def test_sandbox_failure_blocks_before_exec(self):
        self.linked_worktree()
        marker = self.root / "exec-started"
        env = self.fake_codex(f"Path({str(marker)!r}).touch()")
        shim = self.root / "codex"
        shim.write_text(shim.read_text().replace("if 'sandbox' in sys.argv[1:]: sys.exit(0)",
                                                "if 'sandbox' in sys.argv[1:]: sys.exit(1)"))
        self.dispatch(env, code=1)
        log = json.loads(self.record_path("latest-dispatch.json").read_text())
        self.assertEqual(log["sandbox_check"]["outcome"], "failed")
        self.assertNotIn("execution", log)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()

import json
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import feedback_loop
import test_coordinator as fixtures


class FeedbackLoopTest(unittest.TestCase):
    git = fixtures.CoordinatorTest.git
    linked_worktree = fixtures.CoordinatorTest.linked_worktree
    fake_codex = fixtures.CoordinatorTest.fake_codex
    cli = fixtures.CoordinatorTest.cli
    cli_result = fixtures.CoordinatorTest.cli_result

    def setUp(self):
        fixtures.CoordinatorTest.setUp(self)
        self.linked_worktree()
        self.record = self.scope.parent / "development-coordinator" / "feedback-loop.json"
        self.command = ["python3", "-B", "-c",
                        f"from pathlib import Path; assert Path({fixtures.AGENT!r}).read_text() == 'answer = 42\\n'"]

    def models(self, implementation=None, review=None):
        source = "source = Path(" + repr(fixtures.AGENT) + ")\n"
        if implementation is None:
            implementation = "source.write_text('answer = 42\\n')"
        review = review or "dict(decision='accept', findings='Checked the change and the acceptance test.')"
        body = ("prompt = sys.stdin.read()\n"
                "if '--output-last-message' in sys.argv:\n"
                "    assert 'Independently review' in prompt and 'test_log' in prompt\n"
                "    assert not list(Path('.').iterdir())\n"
                f"    Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text(json.dumps({review}))\n"
                "    sys.exit(0)\n" + source + implementation)
        env = self.fake_codex(body)
        # Execute the real pinned test program. Isolation itself needs the live kernel/CLI check.
        shim = self.root / "codex"
        shim.write_text(shim.read_text().replace(
            "if 'sandbox' in sys.argv[1:]: sys.exit(0)",
            "if 'sandbox' in sys.argv[1:]:\n"
            "    args = sys.argv[sys.argv.index('--')+1:]\n"
            "    if args[0] == '/usr/bin/env':\n"
            "        os.chdir(sys.argv[sys.argv.index('-C')+1]); os.execv(args[0], args)\n"
            "    sys.exit(0)"))
        return env

    def args(self, *options):
        return ("loop", self.issue, fixtures.BRANCH, self.base, "--worktree", self.repo,
                "--test-argv", json.dumps(self.command), *options)

    def launch(self, env, *options, code=0):
        self.cli(*self.args(*options), env=env, code=code)
        return json.loads(self.record.read_bytes())

    def test_first_pass_and_repeated_resume(self):
        env = self.models()
        run = self.launch(env)
        self.assertEqual((run["status"], run["calls"], run["retries"]), ("READY_FOR_PR", 2, 0))
        self.assertEqual(run["head"], self.git("rev-parse", "HEAD"))
        self.assertEqual(run["changed_files"], [fixtures.AGENT])
        self.assertEqual(run["attempts"][0]["test"]["returncode"], 0)
        self.cli("loop-resume", env=env)
        self.assertEqual(run, json.loads(self.record.read_bytes()))

    def test_failing_test_feedback_then_pass(self):
        env = self.models("source.write_text('answer = 42\\n' if 'Fix the constant' in prompt else 'answer = 40\\n')",
                          "dict(decision='revise', findings='Fix the constant') if 'AssertionError' in prompt else "
                          "dict(decision='accept', findings='Verified corrected answer')")
        run = self.launch(env)
        a, b = run["attempts"]
        self.assertEqual((run["calls"], run["retries"]), (4, 1))
        self.assertEqual(a["failure_category"], "code")
        self.assertEqual(b["test"]["outcome"], "passed")
        self.assertEqual(self.git("rev-parse", "HEAD^"), a["head"])
        self.assertEqual(json.loads(self.scope.read_text())["base"], self.base)

    def test_diff_check_forces_revision(self):
        self.command = ["python3", "-c", f"import runpy; assert runpy.run_path({fixtures.AGENT!r})['answer'] == 42"]
        env = self.models("source.write_text('answer = 42' + ('' if 'trailing whitespace' in prompt else '  ') + '\\n')")
        run = self.launch(env)
        first, second = run["attempts"]
        self.assertEqual(first["test"]["returncode"], 0)
        self.assertNotEqual(first["diff_check"]["returncode"], 0)
        self.assertEqual(second["diff_check"]["returncode"], 0)

    def test_missing_input(self):
        missing = str(Path(fixtures.AGENT).with_name("absent.py"))
        run = self.launch(self.models(), "--test-input", missing, code=1)
        self.assertEqual(run["status"], "BLOCKED_ENV")
        self.assertIn(missing, run["cause"]["reason"])
        self.assertEqual((run["calls"], run["head"]), (0, self.base))

    def test_scope_violation(self):
        run = self.launch(self.models("source.write_text('bad'); Path('forbidden').touch()"), code=1)
        self.assertEqual(run["cause"]["category"], "permission")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        self.assertIn("forbidden", run["cause"]["reason"])
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_no_change(self):
        run = self.launch(self.models("print('PASS')"), code=1)
        self.assertEqual(run["status"], "FAILED")
        self.assertEqual(run["attempts"][0]["dispatch"]["outcome"], "TASK_NOT_COMPLETED")

    def test_failed_regressions_override_accept_and_exhaust_retries(self):
        run = self.launch(self.models("source.write_text(source.read_text() + '# wrong\\n')"), code=1)
        self.assertEqual((run["status"], run["calls"], run["retries"]), ("FAILED", 6, 2))
        self.assertTrue(all(a["test"]["returncode"] for a in run["attempts"]))

    def test_durable_receipt_and_scrubbed_test_environment(self):
        evidence = self.root / "private"
        evidence.mkdir(mode=0o700)
        self.command = ["python3", "-B", "-c", "import os; assert 'OPENAI_API_KEY' not in os.environ"]
        run = self.launch(self.models(), "--evidence-dir", str(evidence))
        self.assertTrue(Path(run["attempts"][0]["receipt"]).is_relative_to(evidence))
        self.assertEqual(run["status"], "READY_FOR_PR")

    def test_inference_process_failure(self):
        run = self.launch(self.models("print('model disconnected'); sys.exit(9)"), code=1)
        self.assertEqual(run["cause"]["category"], "model")
        self.assertEqual(run["attempts"][0]["dispatch"]["execution"]["returncode"], 9)

    def test_budget(self):
        run = self.launch(self.models(), "--max-calls", "1", code=1)
        self.assertEqual((run["calls"], run["cause"]["category"]), (1, "budget"))

    def test_completed_resume_checks_candidate_again(self):
        env = self.models()
        self.launch(env)
        (self.repo / fixtures.AGENT).write_text("answer = 0")
        self.cli("loop-resume", env=env, code=1)
        self.assertEqual(json.loads(self.record.read_bytes())["status"], "BLOCKED")

    def test_empty_regression_suite(self):
        self.command = ["python3", "-B", "-m", "unittest", "discover"]
        run = self.launch(self.models(), code=1)
        self.assertEqual(run["cause"]["category"], "test")

    def test_deadline(self):
        run = self.launch(self.models("time.sleep(10)"), "--timeout", "1", code=1)
        self.assertEqual(run["cause"]["category"], "budget")
        self.assertLess(time.time() - run["started_at"], 4)

    def test_invalid_review(self):
        run = self.launch(self.models(review="dict(decision='accept', allowed_files=['prod.py'])"), code=1)
        self.assertEqual(run["cause"]["category"], "model")

    def test_external_criterion_review_and_workflow_gate(self):
        name = "Independent workflow oracle"
        issue = json.loads(self.issue.read_bytes())
        issue["body"] += " Completion requires the Independent workflow oracle and READY_FOR_PR."
        self.issue.write_text(json.dumps(issue))
        review = ("dict(decision='accept', findings='Code verified, oracle pending') "
                  "if 'coordinator_checks' in prompt and 'Independent workflow oracle' in prompt "
                  "else dict(decision='block', findings='External evidence missing')")
        run = self.launch(self.models(review=review), "--workflow-check", name, json.dumps(self.command))
        result = run["attempts"][0]["workflow_results"][name]
        self.assertEqual(run["completion"]["workflow_run_ids"][name], result["test"]["run_id"])
        self.assertNotEqual(result["test"]["run_id"], run["completion"]["acceptance_run_id"])
        self.assertEqual(result["test"]["head"], run["completion"]["head"])
        self.assertEqual((run["calls"], run["retries"]), (2, 0))

    def test_unavailable_workflow_evidence_blocks_accepted_code(self):
        run = self.launch(self.models(), "--workflow-check", "Full system suite", "null", code=1)
        self.assertEqual((run["reviewer"]["decision"], run["cause"]["category"]), ("accept", "evidence"))
        self.assertIn("Full system suite", run["cause"]["reason"])
        self.assertNotIn("completion", run)
        args = ("review", fixtures.ISSUE, fixtures.BRANCH, self.base, run["attempts"][0]["receipt"], "accept", "OK")
        self.assertIn("loop-resume", self.cli(*args, code=1))

    def test_failing_workflow_receipt_blocks(self):
        cmd = ["python3", "-c", "raise SystemExit(9)"]
        run = self.launch(self.models(), "--workflow-check", "oracle", json.dumps(cmd), code=1)
        self.assertEqual(run["attempts"][0]["workflow_results"]["oracle"]["test"]["returncode"], 9)
        self.assertEqual((run["status"], run["cause"]["phase"]), ("BLOCKED", "complete"))

    def test_unmapped_evidence_cannot_be_accepted(self):
        env = self.models(review="dict(decision='unverified', findings='Unmapped requirement: full suite')")
        run = self.launch(env, code=1)
        self.assertEqual((run["status"], run["cause"]["category"]), ("BLOCKED", "evidence"))

    def test_genuine_code_block_is_preserved(self):
        env = self.models(review="dict(decision='block', findings='Required edge case is missing')")
        run = self.launch(env, code=1)
        self.assertEqual(run["status"], "BLOCKED")
        self.assertIn("edge case", run["cause"]["reason"])

    def test_resume_rejects_replaced_review_execution(self):
        env = self.models()
        run = self.launch(env)
        record = Path(run["attempts"][-1]["review_execution"])
        review = json.loads(record.read_bytes())
        review["head"] = self.base
        record.write_text(json.dumps(review))
        self.cli("loop-resume", env=env, code=1)
        final = json.loads(self.record.read_bytes())
        self.assertEqual((final["cause"]["category"], final["calls"]), ("evidence", 2))
        self.assertNotIn("completion", final)

    def test_resume_rejects_swapped_workflow_receipt(self):
        env = self.models()
        run = self.launch(env, "--workflow-check", "oracle", json.dumps(self.command))
        attempt = run["attempts"][0]
        Path(attempt["workflow_results"]["oracle"]["receipt"]).write_bytes(Path(attempt["receipt"]).read_bytes())
        self.cli("loop-resume", env=env, code=1)
        self.assertEqual(json.loads(self.record.read_bytes())["cause"]["category"], "evidence")

    def test_interrupted_review_resumes_with_original_test_and_budget(self):
        marker = self.root / "review-interrupted"
        # Hold the fake reviewer at a known boundary. Also reproduce shells that
        # start background commands with SIGINT ignored across exec.
        env = self.models(review=f"(Path({str(marker)!r}).touch(), time.sleep(12))[1]")
        old = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            proc = subprocess.Popen([sys.executable, "-B", fixtures.SCRIPT, *map(str, self.args("--timeout", "15"))],
                                    cwd=self.repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        finally:
            signal.signal(signal.SIGINT, old)
        try:
            deadline = time.monotonic() + 10
            while not marker.exists() and time.monotonic() < deadline and proc.poll() is None:
                time.sleep(0.01)
            self.assertTrue(marker.exists(), "Reviewer did not reach its execution barrier.")
            reserved = json.loads(self.record.read_bytes())
            self.assertEqual((reserved["phase"], reserved["calls"]), ("review", 2))
            proc.send_signal(signal.SIGINT)
            output, _ = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 130, output)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.communicate()
        partial = json.loads(self.record.read_bytes())
        self.assertEqual(partial, reserved)
        self.cli("loop-resume", env=self.models())
        run = json.loads(self.record.read_bytes())
        self.assertEqual((run["calls"], run["status"]), (3, "READY_FOR_PR"))
        self.assertEqual(partial["attempts"][0]["receipt"], run["attempts"][0]["receipt"])

    def prepare_self_development(self):
        directory = self.repo / feedback_loop.scope.COORDINATOR_DIRECTORY
        directory.mkdir(parents=True)
        runtime = Path(feedback_loop.__file__).parent
        for name in feedback_loop.scope.TRUSTED_RUNTIME_FILES:
            (directory / name).write_bytes((runtime / name).read_bytes())
        self.git("add", str(directory))
        self.git("commit", "-qm", "Fixture trusted Coordinator baseline")
        self.base = self.git("rev-parse", "HEAD")
        agent_grant = json.loads(self.scope.read_text())
        self.scope.write_text(json.dumps({**agent_grant, "base": self.base}))
        target = feedback_loop.scope.COORDINATOR_DIRECTORY + "feedback_loop.py"
        approval = self.scope.parent / feedback_loop.scope.SELF_DEVELOPMENT_APPROVAL
        approval.write_text(json.dumps({"issue_url": fixtures.ISSUE, "branch": fixtures.BRANCH,
                                        "base": self.base, "allowed_files": [target]}))
        approval.chmod(0o600)
        self.command = ["python3", "-B", "-c",
                        f"from pathlib import Path; assert Path({target!r}).read_text().endswith('# pilot change\\n')"]
        trusted = self.root / "trusted-runtime"
        trusted.mkdir(mode=0o700)
        for name in feedback_loop.scope.TRUSTED_RUNTIME_FILES:
            destination = trusted / name
            destination.write_bytes((runtime / name).read_bytes())
            destination.chmod(0o600)
        return target, approval, trusted

    def self_models(self, target):
        body = ("prompt = sys.stdin.read()\n"
                "if '--output-last-message' in sys.argv:\n"
                "    Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text("
                "json.dumps(dict(decision='accept', findings='Reviewed the isolated Coordinator pilot.')))\n"
                "    sys.exit(0)\n"
                f"source = Path({target!r})\n"
                "source.write_text(source.read_text() + '# pilot change\\n')\n")
        env = self.fake_codex(body)
        shim = self.root / "codex"
        shim.write_text(shim.read_text().replace(
            "if 'sandbox' in sys.argv[1:]: sys.exit(0)",
            "if 'sandbox' in sys.argv[1:]:\n"
            "    args = sys.argv[sys.argv.index('--')+1:]\n"
            "    if args[0] == '/usr/bin/env':\n"
            "        os.chdir(sys.argv[sys.argv.index('-C')+1]); os.execv(args[0], args)\n"
            "    sys.exit(0)"))
        return env

    def test_self_development_reuses_bounded_loop_and_trusted_runtime(self):
        target, _, _ = self.prepare_self_development()
        env = self.self_models(target)
        run = self.launch(env, "--approval-profile", "coordinator-self-development")
        self.assertEqual((run["status"], run["calls"], run["retries"]), ("READY_FOR_PR", 2, 0))
        self.assertEqual(run["approval_profile"], "coordinator-self-development")
        self.assertEqual(run["changed_files"], [target])
        self.assertEqual(set(run["trusted_runtime"]), {
            feedback_loop.scope.COORDINATOR_DIRECTORY + name
            for name in feedback_loop.scope.TRUSTED_RUNTIME_FILES})
        self.cli("loop-resume", env=env)

    def test_self_development_fails_closed_on_grant_or_runtime_change(self):
        target, approval, _ = self.prepare_self_development()
        with (patch.object(Path, "cwd", return_value=self.repo),
              patch.object(feedback_loop.c, "verify_trusted_runtime",
                           side_effect=ValueError("untrusted runtime"))):
            with self.assertRaisesRegex(ValueError, "untrusted runtime"):
                args = type("Args", (), dict(
                    worktree=self.repo, timeout=10, max_calls=2, test_argv=self.command,
                    workflow_check=[], inputs=[], issue=self.issue, branch=fixtures.BRANCH,
                    base=self.base, evidence_dir=None,
                    approval_profile="coordinator-self-development"))()
                feedback_loop.start(args)
        approval.unlink()
        self.cli(*self.args("--approval-profile", "coordinator-self-development"),
                 env=self.self_models(target), code=1)
        self.assertFalse(self.record.exists())

    def launch_trusted(self, trusted, *controller, base=None, env=None):
        return subprocess.run(
            [sys.executable, "-I", "-B", "-S", str(trusted / "agent_scope.py"),
             str(trusted), str(self.repo), base or self.base, "--", *map(str, controller)],
            cwd=self.repo, env=env, capture_output=True, text=True, timeout=20)

    def test_external_isolated_launcher_imports_only_four_pinned_modules(self):
        target, approval, trusted = self.prepare_self_development()
        injected = self.root / "candidate-injection"
        injected.mkdir()
        marker = self.root / "injected-module-loaded"
        for name in feedback_loop.scope.TRUSTED_RUNTIME_FILES:
            (injected / name).write_text(f"from pathlib import Path; Path({str(marker)!r}).touch()\n")
        env = {**os.environ, "PYTHONPATH": str(injected)}
        result = self.launch_trusted(trusted, "health", env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(marker.exists())
        line = next(line for line in result.stderr.splitlines() if line.startswith("TRUSTED_RUNTIME "))
        attestation = json.loads(line.removeprefix("TRUSTED_RUNTIME "))
        self.assertEqual(attestation["baseline"], self.base)
        self.assertEqual(set(attestation["modules"]), {
            feedback_loop.scope.COORDINATOR_DIRECTORY + name
            for name in feedback_loop.scope.TRUSTED_RUNTIME_FILES})
        self.assertEqual({Path(path).parent for path in attestation["origins"].values()}, {trusted})

        gate = trusted / "external_regression_gate.py"
        original = gate.read_bytes()
        gate.write_bytes(original + b"\n# corrupt\n")
        blocked = self.launch_trusted(trusted, "health", env=env)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("external_regression_gate.py", blocked.stderr)
        gate.write_bytes(original)

        extra = trusted / "candidate_module.py"
        extra.write_text("raise RuntimeError('must not load')\n")
        blocked = self.launch_trusted(trusted, "health", env=env)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("unapproved modules", blocked.stderr)
        extra.unlink()

        blocked = self.launch_trusted(trusted, "health", base="0" * 40, env=env)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("BLOCKED", blocked.stderr)

        grant = json.loads(approval.read_text())
        approval.write_text(json.dumps({**grant, "branch": "research/wrong"}))
        loop = self.launch_trusted(
            trusted, "loop", self.issue, fixtures.BRANCH, self.base,
            "--worktree", self.repo, "--approval-profile", "coordinator-self-development",
            "--test-argv", json.dumps(self.command), "--timeout", "10", "--max-calls", "2",
            env=env)
        self.assertNotEqual(loop.returncode, 0)
        self.assertIn("approval does not match", loop.stderr)
        self.assertFalse(marker.exists())

        approval.write_text(json.dumps(grant))
        candidate_gate = self.repo / feedback_loop.scope.COORDINATOR_DIRECTORY / "external_regression_gate.py"
        candidate_bytes = candidate_gate.read_bytes()
        candidate_gate.write_bytes(candidate_bytes + b"\n# candidate injection\n")
        try:
            loop = self.launch_trusted(
                trusted, "loop", self.issue, fixtures.BRANCH, self.base,
                "--worktree", self.repo, "--approval-profile", "coordinator-self-development",
                "--test-argv", json.dumps(self.command), "--timeout", "10", "--max-calls", "2",
                env=env)
            self.assertNotEqual(loop.returncode, 0)
            self.assertIn("clean worktree", loop.stderr)
        finally:
            candidate_gate.write_bytes(candidate_bytes)


if __name__ == "__main__":
    unittest.main()

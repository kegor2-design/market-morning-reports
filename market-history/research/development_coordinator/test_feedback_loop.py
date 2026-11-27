import json
import os
import time
import unittest
from pathlib import Path

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

    def test_interrupted_review_resumes_with_original_test_and_budget(self):
        marker = self.root / "review-interrupted"
        # Stop the coordinator during the second role, after its call was reserved.
        review = (f"(os.kill(os.getppid(), signal.SIGINT), Path({str(marker)!r}).touch(), "
                  "dict(decision='block',findings='interrupted'))[-1]")
        env = self.models(review=review)
        shim = self.root / "codex"
        shim.write_text(shim.read_text().replace("prompt = sys.stdin.read()", "import signal\nprompt = sys.stdin.read()"))
        result = self.cli_result(*self.args(), env=env)
        self.assertNotEqual(result.returncode, 0)
        partial = json.loads(self.record.read_bytes())
        self.assertEqual((partial["phase"], partial["calls"]), ("review", 2))
        self.cli("loop-resume", env=self.models())
        run = json.loads(self.record.read_bytes())
        self.assertEqual((run["calls"], run["status"]), (3, "READY_FOR_PR"))
        self.assertEqual(partial["attempts"][0]["receipt"], run["attempts"][0]["receipt"])


if __name__ == "__main__":
    unittest.main()

"""Offline fail-closed tests for Coordinator's external evidence gate."""

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import external_regression_gate as gate


class ExternalRegressionGateTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "research/external-gate")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("commit", "-q", "--allow-empty", "-m", "base")
        self.base = self.git("rev-parse", "HEAD")
        (self.repo / "a.py").write_text("answer = 42\n")
        self.git("add", "a.py")
        self.git("commit", "-q", "-m", "candidate")
        self.head = self.git("rev-parse", "HEAD")
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.plan_path = self.root / "plan.json"
        self.plan = {"schema_version": 1, "base_sha": self.base, "candidate_sha": self.head,
                     "baseline_test_ids": {}, "approved_added_ids": {}, "commands": {}}
        for suite in gate.SUITES:
            identity = f"test_{suite}.Tests.test_original"
            self.plan["baseline_test_ids"][suite] = [identity]
            self.plan["approved_added_ids"][suite] = []
            argv = ["python3", "-B", "-m", "unittest", "-v", f"test_{suite}"]
            self.plan["commands"][suite] = argv
            self._save_receipt(suite, [identity], argv)
        self.pin()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def pin(self):
        data = json.dumps(self.plan, sort_keys=True).encode()
        self.plan_path.write_bytes(data)
        self.plan_hash = hashlib.sha256(data).hexdigest()

    def _save_receipt(self, suite, ids, argv=None, *, outcome="passed", skipped=0):
        lines = [f"{name.split('.')[-1]} ({name}) ... {'ok' if not skipped else 'skipped'}" for name in ids]
        lines += ["", "----------------------------------------------------------------------",
                  f"Ran {len(ids)} tests in 0.001s", "", "OK" if not skipped else f"OK (skipped={skipped})"]
        log = ("\n".join(lines) + "\n").encode()
        (self.evidence / f"{suite}.log").write_bytes(log)
        rec = {"schema_version": 1, "suite": suite, "head": self.head,
               "argv": argv or self.plan["commands"][suite], "test_ids": ids,
               "tests_run": len(ids), "failures": 0, "errors": 0, "skipped": skipped,
               "returncode": 0, "outcome": outcome,
               "log_sha256": hashlib.sha256(log).hexdigest(), "execution_id": "run-" + suite}
        self._write_receipt(suite, rec)

    def _write_receipt(self, suite, rec):
        (self.evidence / f"{suite}-receipt.json").write_text(json.dumps(rec))

    def receipt(self, suite):
        return json.loads((self.evidence / f"{suite}-receipt.json").read_text())

    def _git_run(self, argv, **kwargs):
        # patching gate.subprocess.run affects the shared subprocess module; use Popen
        p = subprocess.Popen(argv, cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=kwargs.get("text", True))
        stdout, stderr = p.communicate(timeout=30)
        result = subprocess.CompletedProcess(argv, p.returncode, stdout, stderr)
        if kwargs.get("check") and result.returncode:
            raise subprocess.CalledProcessError(result.returncode, argv, stdout, stderr)
        return result

    def run_gate(self):
        with patch.object(gate, "_git", side_effect=lambda *a: self._git_run(["git", *a], check=True)):
            with patch.object(gate.subprocess, "run", side_effect=self._git_run):
                return gate.verify(self.plan_path, self.plan_hash, self.evidence)


    def test_numeric_unittest_names(self):
        from external_regression_gate import _unittest_log

        names = [
            "test_404_is_not_promoted_to_recovery_task",
            "test_429_requires_new_approval_then_resumes",
            "test_429_retry_after_delay_survives_queue_restart",
            "test_503_recovery_resumes_original_goal_and_never_replays",
        ]

        lines = [
            f"{name} (test_api_recovery.ApiRecoveryDagTests.{name}) ... ok"
            for name in names
        ]

        log = "\\n".join(
            lines + [
                "",
                "----------------------------------------------------------------------",
                f"Ran {len(names)} tests in 0.010s",
                "",
                "OK",
                "",
            ]
        ).replace("\\n", "\n").encode("utf-8")

        expected = {
            f"test_api_recovery.ApiRecoveryDagTests.{name}"
            for name in names
        }

        self.assertEqual(_unittest_log(log), expected)

    def test_verified_receipts(self):
        result = self.run_gate()
        self.assertEqual((result["status"], result["total"], result["approved_new"]), ("VERIFIED", 3, 0))

    def test_approved_addition_exact_name(self):
        suite = gate.SUITES[0]
        new = f"test_{suite}.Tests.test_added"
        self.plan["approved_added_ids"][suite].append(new)
        self._save_receipt(suite, self.plan["baseline_test_ids"][suite] + [new])
        self.pin()
        self.assertEqual(self.run_gate()["approved_new"], 1)

    def test_same_count_renamed_test_blocks(self):
        suite = gate.SUITES[0]
        self._save_receipt(suite, [f"test_{suite}.Tests.test_renamed"])
        with self.assertRaisesRegex(ValueError, "Missing, renamed"):
            self.run_gate()

    def test_skip_blocks(self):
        suite = gate.SUITES[1]
        self._save_receipt(suite, self.plan["baseline_test_ids"][suite], skipped=1)
        with self.assertRaisesRegex(ValueError, "skip mismatch"):
            self.run_gate()

    def test_wrong_candidate_sha_blocks(self):
        suite = gate.SUITES[0]
        rec = self.receipt(suite)
        rec["head"] = self.base
        self._write_receipt(suite, rec)
        with self.assertRaisesRegex(ValueError, "SHA"):
            self.run_gate()

    def test_wrong_git_head_blocks(self):
        self.git("checkout", "-q", self.base)
        with self.assertRaisesRegex(ValueError, "Checkout HEAD"):
            self.run_gate()

    def test_log_mutation_blocks(self):
        with (self.evidence / f"{gate.SUITES[1]}.log").open("ab") as f:
            f.write(b"modified\n")
        with self.assertRaisesRegex(ValueError, "Log hash"):
            self.run_gate()

    def test_receipt_argv_mismatch_blocks(self):
        suite = gate.SUITES[1]
        rec = self.receipt(suite)
        rec["argv"] = ["echo", "passed"]
        self._write_receipt(suite, rec)
        with self.assertRaisesRegex(ValueError, "command"):
            self.run_gate()

    def test_execution_id_duplicate_blocks(self):
        suite = gate.SUITES[1]
        rec = self.receipt(suite)
        rec["execution_id"] = "run-" + gate.SUITES[0]
        self._write_receipt(suite, rec)
        with self.assertRaisesRegex(ValueError, "execution identity"):
            self.run_gate()

    def test_wrong_plan_hash_blocks(self):
        self.plan["candidate_sha"] = self.base
        self.pin()
        self.plan_hash = "f" * 64
        with self.assertRaisesRegex(ValueError, "pinned plan"):
            self.run_gate()

    def test_reject_unknown_suite(self):
        self.plan["baseline_test_ids"]["extra_suite"] = ["test_extra.Tests.test_x"]
        self.pin()
        with self.assertRaisesRegex(ValueError, "suite contracts"):
            self.run_gate()

    def test_dirty_candidate_blocks(self):
        (self.repo / "untracked").write_text("x")
        with self.assertRaisesRegex(ValueError, "not clean"):
            self.run_gate()

    def test_receipt_id_not_in_log_blocks(self):
        suite = gate.SUITES[0]
        rec = self.receipt(suite)
        rec["test_ids"] = ["test_replacement.Tests.test_added"]
        self._write_receipt(suite, rec)
        with self.assertRaisesRegex(ValueError, "Receipt IDs"):
            self.run_gate()

    def test_unapproved_addition_blocks(self):
        suite = gate.SUITES[0]
        self._save_receipt(suite, self.plan["baseline_test_ids"][suite] + ["test_new.Tests.test_added"])
        with self.assertRaisesRegex(ValueError, "unapproved"):
            self.run_gate()

    def test_symlink_log_blocks(self):
        log = self.evidence / f"{gate.SUITES[0]}.log"
        data = log.read_bytes()
        other = self.root / "other.log"
        other.write_bytes(data)
        log.unlink()
        log.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "Symbolic link"):
            self.run_gate()

    def test_cross_suite_duplicate_id_blocks(self):
        first, second = gate.SUITES[:2]
        repeated = self.plan["baseline_test_ids"][first][0]
        self.plan["approved_added_ids"][second] = [repeated]
        self.pin()
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            self.run_gate()

    def test_readonly_git_index(self):
        import os
        index = self.repo / ".git" / "index"
        before = index.read_bytes()
        original_stat = index.stat()
        os.utime(self.repo / "a.py", (1000000000, 1000000000))
        self.assertEqual(self.run_gate()["status"], "VERIFIED")
        self.assertEqual(index.read_bytes(), before)
        self.assertEqual(index.stat().st_mtime_ns, original_stat.st_mtime_ns)

    def test_failed_log_blocks(self):
        suite = gate.SUITES[1]
        log_path = self.evidence / f"{suite}.log"
        log = log_path.read_text().replace(" ... ok", " ... FAIL")
        log_path.write_text(log)
        rec = self.receipt(suite)
        rec["log_sha256"] = hashlib.sha256(log.encode()).hexdigest()
        self._write_receipt(suite, rec)
        with self.assertRaisesRegex(ValueError, "Nonpassing unittest"):
            self.run_gate()


if __name__ == "__main__":
    unittest.main()

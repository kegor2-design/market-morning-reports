"""Fail-closed, read-only verification of externally executed unittest suites.

The operator pins a plan by SHA-256 outside the candidate's edit grant.  Receipts
and logs are still only as trustworthy as the execution host that created them;
this module does not claim cryptographic execution attestation.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

SCHEMA = 1
SUITES = ("universal_agent", "regime190", "development_coordinator")
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
TEST_ID = re.compile(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*){2,}\Z", re.ASCII)
RESULT = re.compile(r"test_[A-Za-z_][\w]* \(([A-Za-z_][\w.]*)\) \.\.\. (.+)\Z", re.ASCII)
RUN_COUNT = re.compile(r"Ran (\d+) tests? in ", re.ASCII)


def add_commands(commands):
    p = commands.add_parser("verify-external-regressions", help="Verify pinned external unittest receipts; read-only.")
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--plan-sha256", required=True)
    p.add_argument("--evidence-dir", type=Path, required=True)


def _read_regular(path, *, limit):
    if path.is_symlink():
        raise ValueError(f"Symbolic link not allowed: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as handle:
        meta = os.fstat(handle.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or meta.st_size > limit:
            raise ValueError(f"Invalid evidence file: {path.name}")
        data = handle.read(limit + 1)
        if len(data) > limit:
            raise ValueError(f"Evidence too large: {path.name}")
        if os.fstat(handle.fileno()).st_size != len(data):
            raise ValueError(f"Evidence changed while reading: {path.name}")
        return data


def _json(raw, label):
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON field in {label}: {key}")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON in {label}") from error


def _ids(values, label):
    if not isinstance(values, list) or not values:
        raise ValueError(f"Empty or invalid test IDs: {label}")
    if any(not isinstance(v, str) or not TEST_ID.fullmatch(v) for v in values):
        raise ValueError(f"Invalid test ID: {label}")
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate test ID: {label}")
    return set(values)


def _unittest_log(raw):
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("Unparseable test log") from error
    found = []
    for line in lines:
        match = RESULT.fullmatch(line.strip())
        if match:
            identifier, outcome = match.groups()
            if outcome != "ok":
                raise ValueError(f"Nonpassing unittest result: {identifier} {outcome}")
            if not identifier.split(".")[-1].startswith("test_"):
                raise ValueError("Unrecognized unittest test identifier")
            found.append(identifier)
    counts = [int(m.group(1)) for line in lines if (m := RUN_COUNT.search(line))]
    if len(counts) != 1 or counts[0] != len(found) or not found:
        raise ValueError("Unittest log test count or verbose test names missing")
    if len(found) != len(set(found)):
        raise ValueError("Duplicate test execution in log")
    if not any(line.strip() == "OK" for line in lines) or any(
        line.startswith(("FAILED", "OK (", "Traceback (most recent", "ERROR:")) for line in lines
    ):
        raise ValueError("Unittest log does not show unconditional PASS")
    return set(found)


def _sha(value, label, pattern):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def _argv(value):
    return (isinstance(value, list) and bool(value) and
            all(isinstance(v, str) and v and "\0" not in v for v in value))


def _git(*argv):
    return subprocess.run(["git", *argv], capture_output=True, text=True, timeout=30, check=True)


def verify(plan_path, plan_sha256, evidence_dir):
    _sha(plan_sha256, "pinned plan digest", DIGEST)
    plan_bytes = _read_regular(plan_path, limit=4 * 1024 * 1024)
    if hashlib.sha256(plan_bytes).hexdigest() != plan_sha256:
        raise ValueError("Operator-pinned plan digest mismatch")
    plan = _json(plan_bytes, "plan")
    if not isinstance(plan, dict) or plan.get("schema_version") != SCHEMA:
        raise ValueError("Invalid plan schema")
    base = _sha(plan.get("base_sha"), "baseline SHA", SHA)
    candidate = _sha(plan.get("candidate_sha"), "candidate SHA", SHA)
    if base == candidate:
        raise ValueError("Candidate must differ from baseline")
    if _git("rev-parse", "--verify", "HEAD^{commit}").stdout.strip() != candidate:
        raise ValueError("Checkout HEAD does not match pinned candidate")
    if _git("--no-optional-locks", "status", "--porcelain", "--untracked-files=all").stdout.strip():
        raise ValueError("Candidate worktree is not clean")
    if subprocess.run(["git", "merge-base", "--is-ancestor", base, candidate],
                      capture_output=True, timeout=30).returncode:
        raise ValueError("Baseline is not an ancestor of candidate")
    baseline = plan.get("baseline_test_ids")
    added = plan.get("approved_added_ids")
    commands = plan.get("commands")
    if any(not isinstance(v, dict) or set(v) != set(SUITES) for v in (baseline, added, commands)):
        raise ValueError("Missing, extra or duplicated suite contracts")
    if not evidence_dir.is_dir() or evidence_dir.is_symlink():
        raise ValueError("Invalid evidence directory")
    before_ids = set()
    after_ids = set()
    execution_ids = set()
    summary = {}
    for suite in SUITES:
        original = _ids(baseline[suite], f"baseline/{suite}")
        additions = _ids(added[suite], f"approved additions/{suite}") if added[suite] else set()
        if (original & additions or before_ids & original or after_ids & additions
                or before_ids & additions or after_ids & original):
            raise ValueError("Overlapping baseline or approved test IDs")
        before_ids.update(original)
        after_ids.update(additions)
        argv = commands[suite]
        if not _argv(argv) or "-v" not in argv or "-q" in argv:
            raise ValueError(f"Suite requires a pinned verbose unittest command: {suite}")
        receipt = _json(_read_regular(evidence_dir / f"{suite}-receipt.json", limit=2 * 1024 * 1024), suite)
        expected_fields = {"schema_version", "suite", "head", "argv", "test_ids", "tests_run",
                           "failures", "errors", "skipped", "returncode", "outcome", "log_sha256", "execution_id"}
        if not isinstance(receipt, dict) or set(receipt) != expected_fields:
            raise ValueError(f"Invalid receipt fields: {suite}")
        if (receipt["schema_version"] != SCHEMA or receipt["suite"] != suite or
            receipt["head"] != candidate or receipt["argv"] != argv or
            receipt["returncode"] != 0 or receipt["outcome"] != "passed" or
            any(type(receipt[k]) is not int or receipt[k] != 0 for k in ("failures", "errors", "skipped"))):
            raise ValueError(f"Receipt outcome, SHA, command or skip mismatch: {suite}")
        if (not isinstance(receipt["execution_id"], str) or not receipt["execution_id"].strip()
                or receipt["execution_id"] in execution_ids):
            raise ValueError("Missing or duplicated execution identity")
        execution_ids.add(receipt["execution_id"])
        log_sha = _sha(receipt["log_sha256"], "log SHA-256", DIGEST)
        raw_log = _read_regular(evidence_dir / f"{suite}.log", limit=8 * 1024 * 1024)
        if hashlib.sha256(raw_log).hexdigest() != log_sha:
            raise ValueError(f"Log hash mismatch: {suite}")
        observed = _unittest_log(raw_log)
        if observed != _ids(receipt["test_ids"], f"receipt/{suite}"):
            raise ValueError(f"Receipt IDs differ from verbose execution log: {suite}")
        if observed != (original | additions):
            raise ValueError(f"Missing, renamed or unapproved test ID: {suite}")
        if type(receipt["tests_run"]) is not int or receipt["tests_run"] != len(observed):
            raise ValueError(f"Test count mismatch: {suite}")
        summary[suite] = len(observed)
    return {"status": "VERIFIED", "candidate_sha": candidate, "base_sha": base,
            "suite_counts": summary, "total": sum(summary.values()), "approved_new": len(after_ids)}


def run(args):
    print(json.dumps(verify(args.plan, args.plan_sha256, args.evidence_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    options = parser.parse_args()
    try:
        raise SystemExit(run(options))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"BLOCKED: {exc}\n")

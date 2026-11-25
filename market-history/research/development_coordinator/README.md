# Development Coordinator Phase 1.5

The coordinator takes a local Issue snapshot, hands it to the local Codex CLI,
runs an operator-selected test, and records a review decision for a Git commit.
`READY_FOR_PR` is a local review result. Publishing requires a separate action.

## Worktree health

From the repository root, run

```bash
python3 market-history/research/development_coordinator/coordinator.py health
```

The command inspects the worktree containing the current directory. It prints
one JSON object with the schema version, checked-out branch, full HEAD commit
SHA and a boolean indicating whether the whole worktree is clean.

```json
{"schema_version": 1, "branch": "main", "head": "0123456789abcdef0123456789abcdef01234567", "clean": true}
```

Both clean and dirty worktrees exit 0. Staged changes, unstaged changes and
untracked files count as dirty. Git ignores excluded files. The check is
read-only and requires only local Git and Python. A detached HEAD, a branch
without a commit, or a Git failure produces a diagnostic on stderr and a
nonzero exit with empty stdout.

## Approving an Agent development task

Use a dedicated registered linked worktree on a clean `research/...` branch.
Use trusted copies of `coordinator.py` and its sibling `agent_scope.py`, Linux,
Python 3.10+, Git and GNU diff. Live execution also requires a local Codex CLI
with named filesystem permissions, the Linux sandbox and an existing ChatGPT
login. The operator supplies a local JSON snapshot with `url`, `state`,
`title` and `body`. Check its provenance, ensure the Issue is open in
`kegor2-design/market-morning-reports`, and inspect its contents for sensitive
data before including it in a model request.

Set `cli` to the absolute path of the trusted script and `issue` to the
snapshot path. From the linked worktree, identify the starting commit and
private approval file.

```bash
worktree=$(git rev-parse --show-toplevel)
branch=$(git branch --show-current)
base=$(git rev-parse HEAD)
admin=$(git rev-parse --absolute-git-dir)
approval="$admin/agent-development-scope.json"
scratch=$(mktemp -d)
```

The operator creates the approval in the **linked worktree’s Git administration
directory**. Each entry grants permission to disclose the entire pinned file
to the ChatGPT-backed CLI and edit its contents. Read each selected file
before approving it. Use sanitized source files and a sanitized Issue. A
Python extension cannot establish that a module contains no embedded secrets.

For example, after deciding on the Issue and one source file, replace the
example URL and filename below. The subshell creates a private approval and
refuses to clobber an existing one. For a revision, explicitly review and
replace the previous approval with the new starting SHA and selected paths.

```bash
issue_url=https://github.com/kegor2-design/market-morning-reports/issues/123
(
  umask 077
  set -C
  python3 - "$issue_url" "$branch" "$base" > "$approval" <<'PY'
import json, sys

print(json.dumps({
    "issue_url": sys.argv[1],
    "branch": sys.argv[2],
    "base": sys.argv[3],
    "allowed_files": ["market-history/research/universal_agent/engine.py"],
}, indent=2))
PY
)
```

The scope must be an operator-owned private regular file with a single link.
There is no default Agent grant. The Coordinator reads approval only from
this fixed location. Issue fields, body instructions and Codex output cannot
add paths. Approval binds the Issue URL, branch and full base SHA. Paths must
name existing tracked Python modules directly under
`market-history/research/universal_agent/` or its immediate `tests/` directory.
Absolute paths, traversal, globs, symlinks, hard links, duplicate paths and
new files fail validation. Checkpoint directories, fixtures, data files,
production paths and the Coordinator itself fall outside this scope.

### Dry run and dispatch

```bash
python3 "$cli" exec "$issue" "$branch" "$base" --worktree "$worktree" --dry-run
```

The dry run validates the registration, clean checkout, approval and actual
source paths and prints the task packet. It invokes neither Codex nor the
login check and creates no dispatch record or candidate edits. `packet`
also renders an Issue for inspection and shows an empty grant if approval
is absent. A registered worktree with ignored or untracked files, hidden
index entries, submodules, or a project-local Codex configuration is
unsuitable for dispatch. Use a fresh worktree for this workflow.

After inspecting the grant and packet, the operator can start a live run.

```bash
python3 "$cli" exec "$issue" "$branch" "$base" --worktree "$worktree" --timeout 900
```

The Coordinator creates a private temporary directory outside the checkout
and copies only approved Git blobs to a fresh workspace at their original
relative paths. It supplies the packet on stdin. The Codex client receives
only HOME, PATH, CODEX_HOME and LANG when set. It uses a ChatGPT login, an
ephemeral session, approval policy `never`, disabled command networking,
and disabled apps, plugins, hooks and web search. Use a trusted CLI and
dedicated local login environment. The client contacts ChatGPT for live
inference. API-key dispatch has no supported path.

The named filesystem profile grants write access to the workspace, requests
minimal platform reads, and grants read-only access to the directory containing
the resolved Codex executable. The ordinary `workspace-write` sandbox alone does
not provide strict per-directory write isolation or protect readable host
files. Before model execution, the Coordinator probes the named profile
with a disposable sibling file, the linked worktree’s Git pointer and a
scratch write. Incompatible sandboxes and failed probes block dispatch.
The probe checks those operations on the local installation. It does not
certify the entire host or CLI. A dry run does not exercise this probe.

The Coordinator inventories the result even on process failure. A passing
process may return content edits only. Additions (including ignored files
and empty directories), removals, renames, links and file-mode changes block
application. It also checks the original checkout, index and approval again.
After validation, it applies a single text patch to the worktree and
checks changed paths and resulting blob IDs. No staging or commit occurs.
A successful dispatch requires at least one verified content change to an
approved file. If Codex exits zero and leaves the approved files identical,
the Coordinator reports `TASK_NOT_COMPLETED` and exits nonzero. A scope
violation still blocks application and records the offending path.
A failure or scope violation leaves partial and unexpected edits in place.
Inspect the reported workspace and the worktree before retrying. The
Coordinator never resets, stashes or cleans either location. Private
temporary run directories remain available until the operator removes them
or the host expires them.

### Candidate verification and review

Inspect all changes and test code before manually committing a candidate.
Run the operator-selected acceptance test from the intended directory
against that clean commit. Use a fresh receipt path for each test.

```bash
python3 "$cli" test --timeout 300 "$branch" "$scratch/attempt1.json" -- \
  python3 -B -m unittest discover -s market-history/research/development_coordinator -v
```

Review the diff between the original base and the tested candidate and
record findings. A failed test can still support a revision request.

```bash
python3 "$cli" review "$issue_url" "$branch" "$base" "$scratch/attempt1.json" \
  revise "$review_findings"
```

For another implementation pass, pin the new approval and dispatch to the
clean revision commit. Keep the original review base. Include earlier
edited paths in the final approval if they remain in the candidate diff.
Retest after the operator commits the corrected candidate.

```bash
python3 "$cli" test "$branch" "$scratch/attempt2.json" -- \
  python3 -B -m unittest discover -s market-history/research/development_coordinator -v
python3 "$cli" review "$issue_url" "$branch" "$base" "$scratch/attempt2.json" \
  accept "$review_summary"
```

For scoped candidates, acceptance also verifies the latest successful
dispatch, approval binding, candidate ancestry, net changed paths and
dispatched file contents. Manual changes to the dispatched result require
a fresh approved run. Review also rejects earlier successful dispatch records
with an empty change list. Standalone Phase 1 test and review remain available
in worktrees without a bridge approval or dispatch.

## Evidence and decisions

- Each worktree stores coordinator records under its own Git directory in
  `development-coordinator/`. Use `git rev-parse --absolute-git-dir` to find
  it. A per-worktree lock serializes test, dispatch and review. A competing
  command exits with an error.
- A test invalidates prior evidence before launch. The record contains a run
  ID, argv, cwd, branch, Git HEAD and porcelain status before and after,
  Unix start/end times, elapsed seconds, timeout, outcome, exit code and the
  last 8 KiB of combined output. The full test output goes to stdout. Launch
  failure has a null exit code. A timeout kills the process group and records
  the timeout separately from an ordinary nonzero or signal exit.
- Use a fresh external receipt path for each attempt. Dirty files, a changed
  HEAD or failed verification block receipt publication. Inspect
  `latest-test.json` for the error. A completed invocation on a stable tree
  can produce a failure receipt. Receipts left by an interrupted publication
  cannot approve a candidate without the matching completed local record.
- Review requires an exact match with the latest coordinator record in that
  worktree, matching clean Git snapshots, the expected ancestry, and a finish
  time within the past **60 minutes**. Retry after expiry, a new commit or a
  failed attempt. External JSON from the older pilot requires a fresh test.
- `READY_FOR_PR` requires a passing process and an explicit `accept` with
  review notes. `REVISION_REQUESTED` records the reviewer's findings.
  `BLOCKED` exits nonzero and reports the reason. `latest-review.json` records
  the decision at review time. Re-run the gate before using an old decision.
  `latest-dispatch.json` records dispatch errors, timeout or exit status.
  It retains the approved paths, workspace location, sandbox probe, process
  result and repository checks. Read `execution.outcome` and
  `execution.returncode` for the Codex process result and the top-level
  `outcome` for the dispatch decision. A new dispatch invalidates the previous review.
  The local records are replaced on the next corresponding action.

## Trust and integration limits

The local operator, coordinator, Git, Codex installation and selected test
command are trusted. Local records help detect a fabricated or edited receipt.
A process running as the same OS user can also change Git metadata, the clock,
the coordinator or its records. These files provide no tamper-proof audit
trail. The gate records the operator's review decision. The operator remains
responsible for its quality and test coverage (including empty suites). Run
with exclusive use of the worktree, Git metadata and temporary directories.
Coordinator locking serializes Coordinator actions only. Endpoint checks
cannot detect transient writes restored before inspection. Test commands run as the
local user, outside the Codex sandbox. Their output can contain sensitive
data. Use a trusted test environment and private evidence paths.

GitHub Issue retrieval/creation, comments, push, draft PR creation and merge
are unimplemented in the coordinator. Commits and code review are manual.
The earlier 2026-11-24 pilot reported GitHub write denial and a Codex Cloud
authentication failure. The local workflow uses ChatGPT-authenticated
`codex exec` and has no Cloud dispatch dependency.

## Regression verification

From the repository root run

```bash
python3 -B -m unittest discover -s market-history/research/development_coordinator -v
```

The suite uses disposable repositories, synthetic Agent files, local Git
commits and a stand-in for the Codex CLI. It covers the Phase 1 gates,
approval binding, dry-run behavior, allowed and forbidden modifications,
traversal, symlinks, hard links, renames, unexpected and ignored files,
partial failures and the manual candidate review path. A passing fixture
suite supplies no evidence of live ChatGPT-backed dispatch.

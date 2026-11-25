# Development Coordinator Phase 1

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

## Local workflow

Use Linux, Python 3.10+, Git and a trusted copy of `coordinator.py`. Dispatch
also requires a compatible local Codex CLI (options checked with 0.171.0)
and an existing ChatGPT login. The operator supplies an Issue JSON file with
`url`, `state`, `title` and `body`. The URL must identify an Issue in
`kegor2-design/market-morning-reports` and the snapshot state must be `OPEN`.
The operator is responsible for the snapshot's provenance and currency.

Start in the approved linked worktree on a clean `research/...` branch. Set
`cli` to the absolute path of the trusted coordinator and `issue` to the
snapshot. Keep the same `base` for review throughout the pilot. Inspect the
packet before dispatching it.

```bash
worktree=$(git rev-parse --show-toplevel)
branch=$(git branch --show-current)
base=$(git rev-parse HEAD)
scratch=$(mktemp -d)
issue_url=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["url"])' "$issue")
python3 "$cli" packet "$issue" "$branch" "$base" > "$scratch/task.md"
python3 "$cli" exec "$issue" "$branch" "$base" --worktree "$worktree" --timeout 900
```

The explicit worktree path is the operator's dispatch approval. The coordinator
checks it against Git's current root and linked-worktree registration, checks
the branch and starting SHA, and verifies the login with `codex login status`.
It sends Issue text to `codex exec` on stdin. The argument array fixes the
working directory, workspace-write sandbox and approval policy. The child gets
only HOME, PATH, CODEX_HOME and LANG when set. The invocation disables extra
writable roots, temporary-directory writes by model commands, command network
access, hooks, apps and plugins. A project-local Codex config blocks dispatch.
The Codex client itself uses the ChatGPT service during a live task.

Inspect the diff and test code after dispatch, including partial edits after a
timeout or error. When the operator has committed a candidate, run its
acceptance test from the intended working directory. The coordinator expects a
clean commit descended from the original base at review time. The example
command exercises the coordinator's own regression suite. Select a command
that checks the actual Issue's acceptance criteria.

```bash
python3 "$cli" test --timeout 300 "$branch" "$scratch/attempt1.json" -- \
  python3 -m unittest discover -s market-history/research/development_coordinator -v
```

Review the diff between the base and the tested candidate. Supply an explicit
decision and substantive findings. After a failed test the operator can still
request a revision using the recorded failure.

```bash
python3 "$cli" review "$issue_url" "$branch" "$base" "$scratch/attempt1.json" \
  revise "$review_findings"
```

For another implementation pass, dispatch from the clean revision starting SHA
and include the review findings in the local task specification. Keep the
original base for the final review. Retest with a new receipt filename after
the operator prepares the corrected candidate. An infrastructure failure can
also be retried on the same commit.

```bash
python3 "$cli" test "$branch" "$scratch/attempt2.json" -- \
  python3 -m unittest discover -s market-history/research/development_coordinator -v
python3 "$cli" review "$issue_url" "$branch" "$base" "$scratch/attempt2.json" \
  accept "$review_summary"
```

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
  The local records are replaced on the next corresponding action.

## Trust and integration limits

The local operator, coordinator, Git, Codex installation and selected test
command are trusted. Local records help detect a fabricated or edited receipt.
A process running as the same OS user can also change Git metadata, the clock,
the coordinator or its records. These files provide no tamper-proof audit
trail. The gate records the operator's review decision. The operator remains
responsible for its quality, test coverage (including empty suites), ignored
files and avoiding concurrent edits by other tools. Test commands run as the
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
python3 -m unittest discover -s market-history/research/development_coordinator -v
```

The suite creates disposable repositories and commits, runs real test
subprocesses, and checks revisions, retries, forgery, SHA and age mismatches,
worktree changes, missing review, concurrent attempts and process failures.
Dispatch tests use a local CLI stand-in inside a registered linked worktree.
They check login rejection, sandbox arguments, stdin handling and process
outcomes. A separate offline probe with the installed Codex 0.171.0 sandbox
and the same workspace-write settings allowed a file inside the temporary
workspace and denied a sibling file. A live ChatGPT-backed edit in a linked
worktree remains a separate end-to-end pilot.

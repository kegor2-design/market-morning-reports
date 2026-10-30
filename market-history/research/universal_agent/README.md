# Universal Research Agent: minimum common engine

Phase 4/5 now adds a bounded supervisor and real read-only Codex integration;
see [SUPERVISOR.md](SUPERVISOR.md) and the
[Regime190 execution audit](../regime190/phase45_report_20261031.md). The
Phase 2 notes below describe the original baseline and remain available for
compatibility. The original Phase 2 and Phase 3 CLIs are unchanged.

This package coordinates evidence-based research tasks for any project with a versioned JSON manifest. It selects the next ready task by priority and dependency, runs only registered read-only checks, records the evidence and status transitions, and resumes from an atomic private checkpoint. It does not modify source data, run SQL writes, spawn shell commands, restart services, or submit a backtest. A project's research work stays in its own collectors and analysis code; this engine verifies milestones and prevents unsupported completion claims.

## Current integration and boundaries

`regime190.project.json` is the first project manifest. It reads the existing Regime190 SQLite checkpoint, 190-row inventory and published audit summary. On the server at Phase 2 baseline, the first three checks complete, `collection_complete` is `BLOCKED` because the two published flags are false, and `pit_complete` remains `PENDING` on that dependency. Both final milestones also carry a `review_required` check, so a summary claim alone can never complete them. This is an engine smoke run, **not** a claim that the Regime190 data goal is complete. The current private state is stored under `~/MyDream2000/research/universal_agent/regime190-v2/state.json`; the initial prototype state under `regime190/` is retained for audit and not reused with the revised manifest. The existing Regime190 `progress.json` and checkpoint are unchanged.

Run from `market-history/research`:

```bash
python3 -m universal_agent plan --project universal_agent/regime190.project.json --state-dir ~/MyDream2000/research/universal_agent/regime190-v2
python3 -m universal_agent run --project universal_agent/regime190.project.json --state-dir ~/MyDream2000/research/universal_agent/regime190-v2 --max-steps 5
```

`plan` does not write state. `run` evaluates at most the requested number of ready tasks and writes a private checkpoint. Evidence mismatch becomes `BLOCKED`; malformed or inaccessible evidence becomes `FAILED`. A previously interrupted task is recorded as `FAILED` before its safe probe is retried. A task is recorded as `VERIFIED` before `COMPLETED`; the event log preserves both transitions. Repeated blocked or failed probes stop after three attempts. After source evidence changes, explicitly reopen that task and rerun it:

```bash
python3 -m universal_agent reopen --project universal_agent/regime190.project.json --state-dir ~/MyDream2000/research/universal_agent/regime190-v2 --task collection_complete
```

Reopen retains the event history. Changing the project manifest hash fails closed; review the old state and choose a new state directory for a new manifest version. The state directory uses an exclusive process lock and atomic, mode-600 state files. Evidence paths must remain inside the configured workspace root. SQLite opens in `mode=ro` with `query_only=ON`; only table counts and integrity checks are allowed. The other probe types are file existence, JSON value equality, CSV unique-row count and a `review_required` gate that always fails until replaced by an independent verifier. There is no arbitrary SQL, shell, network or Python plugin execution.

The installed `regime190-collection.service` and `regime190-publish.timer` are independent. No universal-agent unit or timer was installed, and the user systemd bus remains unavailable from this session. The existing MyDream2000 and MarketMorningPublisher dirty worktrees and untracked `phase2_baseline.py` were left untouched. Operating DB schema, trading engine and service configuration were not changed.

## Codex integration decision

The local `codex exec` command exists and supports `read-only`, `workspace-write` and `danger-full-access` sandbox choices. [Official OpenAI documentation](https://developers.openai.com/codex/non-interactive-mode) describes `codex exec` for bounded noninteractive jobs and says its default sandbox is read-only. This minimum engine does not invoke Codex or read its credentials. A future adapter can propose bounded research tasks to Codex in an isolated worktree after an explicit action policy and approval boundary are implemented; it must never treat a model message as verification evidence. No scheduler or production deployment is part of this change.

## Verification

`python3 -m unittest discover -s market-history/research/universal_agent/tests -v` exercises dependency order, restart/resume, bounded retries, path and SQL rejection, manifest-change refusal, and reopening after new evidence. `python3 -m compileall -q market-history/research/universal_agent` checks compilation. The Regime190 smoke run records actual evidence and leaves its data sources unchanged.

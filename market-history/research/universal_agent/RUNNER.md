# Phase 3 autonomous runner

`runner.py` adds a bounded execution loop to the Phase 2 evidence engine. The Phase 2 CLI, project schema and tests remain available. A version 2 project manifest registers a goal, success criteria, scoped evidence paths, task plan, risk category and resource limits. The runner selects the highest-priority task whose dependencies are complete, records `IN_PROGRESS`, calls Codex only for an explicitly enabled read-only project, checks independent evidence, and saves the result under an exclusive project lock. `COMPLETED` requires passing checks; a model answer alone never passes a gate.

## Regime190

`regime190.runner.json` is the project adapter. It registers the Phase 1 priority task `investigate_price_cutoff_20260915` before historical market membership and PIT validation. Its data checks use the existing private SQLite checkpoint in read-only mode. The Phase 1 checkpoint is left intact. On this server, `inspect`, `plan` and `dry-run` selected the cutoff task; SQLite integrity was `ok`, while independent source-lineage review remained open. Regime190 sets `codex_execution_enabled=false`, so `run-once` records `BLOCKED_APPROVAL` without launching Codex or modifying source data. The runner state is private at `~/MyDream2000/research/universal_agent/regime190-runner-v2/state.json`. The earlier prototype runner state remains preserved in `regime190-runner/` and is not reused after the manifest changed.

From `market-history/research`:

```bash
python3 -m universal_agent.runner_cli inspect --project universal_agent/regime190.runner.json --state-dir ~/MyDream2000/research/universal_agent/regime190-runner-v2
python3 -m universal_agent.runner_cli plan --project universal_agent/regime190.runner.json --state-dir ~/MyDream2000/research/universal_agent/regime190-runner-v2
python3 -m universal_agent.runner_cli dry-run --project universal_agent/regime190.runner.json --state-dir ~/MyDream2000/research/universal_agent/regime190-runner-v2
python3 -m universal_agent.runner_cli status --project universal_agent/regime190.runner.json --state-dir ~/MyDream2000/research/universal_agent/regime190-runner-v2
```

`inspect` and `status` read only. `plan` generates and checkpoints a plan from registered tasks, dependencies, statuses, goal and success criteria; it previews the selected task's current evidence and records status, selection or evidence changes with a reason. `dry-run` selects a task and evaluates its read-only checks without invoking Codex or changing state. `run-once` attempts one task. `resume` advances up to the configured iteration and time limits, stopping on failed, blocked or approval-bound work. A previous `IN_PROGRESS` record is marked interrupted and retried only when its attempt count allows it; completed work is skipped. Network and provider failures may retry at most three times. Authentication, code, quality, verification, permission and resource failures do not silently retry.

## Execution boundary

The local binary is `codex-cli 0.166.0`; `codex login status` reported ChatGPT login. Its installed `exec --help` confirms `--sandbox read-only`, `--json`, `--ephemeral`, `-C`, `--output-schema` and `-o`. The runner checks those options and login before every real invocation. The [official OpenAI non-interactive documentation](https://developers.openai.com/codex/non-interactive-mode) supports `codex exec` and a read-only default. The runner uses an ephemeral scratch Git repository and passes only sanitized task text, an explicit `read-only` sandbox, and an allowlisted child environment. It never uses an approval-bypass flag or an arbitrary shell command from a manifest. Source evidence checks are restricted to declared `data_access` paths.

The separate, harmless CLI smoke project reached the installed executable but **did not start a Codex turn**: `~/.codex/rules/default.rules` has a Starlark parse error near line 977. The runner classified it as a nonretryable `CODE` failure and saved `Codex execpolicy parse error at default.rules:977`. It did not use `--ignore-rules`, change the rule file, or relax sandbox/approval settings. Repairing that user-level rule file requires a separate review before real Codex execution can be validated.

Project limits cover runtime, iterations, retries, one concurrent task, minimum disk free space, runner state artifact size, captured log size and Codex invocation count per run. The external-call limit counts CLI invocations, not internal inference requests or provider API calls. Captured output is rejected if it exceeds the configured byte limit; it is not a hard OS memory cap. A read-only Codex sandbox and scratch repository do not provide a separate OS identity or container, so sensitive host files still need an independent isolation design before broader autonomous deployment. No service or scheduler has been installed.

The task plan is generated from registered task templates and evidence status. It does not invent new research tasks from a model response. A future planner may propose new tasks only after a typed schema, capability review and evidence validation are added. `review_required` keeps the Regime190 source-lineage and PIT milestones open until independent verification exists. PIT-untested data remains excluded from backtesting.

## Verification

`python3 -m unittest discover -s market-history/research/universal_agent/tests -v` covers project registration, priority/dependency selection, both CLIs' existing behavior, mock Codex execution, retry bounds, interrupted checkpoints, duplicate-run locks, approval blocking, data scope, dry-run, run-once and resume. Existing Regime190 tests and Python compilation are separate checks. Operating DB schema, service files, raw data and operating trading code are unchanged.

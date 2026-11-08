# Universal Autonomous Research Agent: PART 1/2 continuation, 2026-11-07

## Baseline and scope

The local and remote `research/universal-autonomous-engine-20261102` heads were `eb9aea6`.
The supplied `603051abae1d930d32aa30e91e08b2c5e33ee338` object and the two named
`autonomous-core-*` branches were absent locally and from `git ls-remote --heads origin`.
Work therefore started in a separate worktree on
`research/autonomous-core-recovery-20261107`. Main, MyDream2000 trading code,
MarketMorningPublisher, operating DB rows/schema, cron and systemd were not edited.

This is a continuation of the existing implementation, not a claim that the complete
PART 1/2 goal has been met. The older Agent 4.3 memory records three real Codex calls;
the Universal coordinator has still made **zero** Codex calls in this branch.

## Function audit

| Requested function | Observed call path | Status after this change |
| --- | --- | --- |
| Goal interpretation | `autonomous.ResearchGoal` → fixed `DOMAINS`; `runner.load_runner_project` goal manifest | PARTIALLY_IMPLEMENTED: no general goal decomposition |
| AI hypothesis and code generation | `regime190.agent43_engine._codex` → schema → `_check_code` | IMPLEMENTED_NOT_CONNECTED to Universal; old Regime190 evidence only |
| Research planning and next task | `supervisor._select`, `_refresh`; `autonomous.run` fixed three domains | PARTIALLY_IMPLEMENTED: evidence ranking and dependency selection, no open-ended new task generation |
| Data requirements and acquisition | Agent 4.3 `_stage_pit`, `_stage_market`; `offline_worker` registered tasks | PARTIALLY_IMPLEMENTED: task-specific local snapshots, no generic provider acquisition |
| PIT validation | `eligibility_manifest`, Agent 4.3 `_verify_pit` | PARTIALLY_IMPLEMENTED: 0/190 verified; missing release/vintage evidence |
| Static code and secure execution | Agent 4.3 `_check_code`, `_isolated_python`; new `self_repair.probe_secure_runner` | IMPLEMENTED_NOT_CONNECTED to Universal research execution |
| Backtest and result assessment | `autonomous.PLUGINS[*].evaluate` → `run` result hashes | PARTIALLY_IMPLEMENTED: three exploratory templates, no independent holdout |
| Error detection, classification, planning | New `self_repair.run_stage`, `diagnose` → `autonomous.run`; `supervisor.operate` failure path | IMPLEMENTED_AND_CONNECTED for these two existing entry points |
| Automatic research code repair | New `repair_research_source` → Agent 4.3 `_check_code` → caller's secure verifier | PARTIALLY_IMPLEMENTED: bounded candidate rollback; no AI candidate supplier wired |
| Checkpoint, STOP, resume, duplicate lock | `engine.locked_state`, `write_state`; `autonomous.run`; `supervisor.operate` | IMPLEMENTED_AND_CONNECTED; interrupted generated script patch now restores durable backup |
| GitHub synchronization | Human-operated Git; `runner.classify` and supervisor failure record | PARTIALLY_IMPLEMENTED: HTTP 403/DNS handling, no autonomous safe push workflow |

## Changes and real checks

- Added a typed failure record, secret redaction, contextual error categories, bounded
  retry decisions and repeated-failure fingerprints in `self_repair.py`.
- Connected calculation failures to Universal checkpoints. A failed domain records
  diagnosis and next action while independent domains continue. The supervisor now
  continues independent tasks after Codex failures, classifies HTTP 403 as approval
  blocked, and retains DNS/network failures for bounded retry. Failed execution
  records are redacted before persistence.
- Added bounded generated `experiment.py` repair in a research tree. It reuses Agent
  4.3's AST/static gate, preserves a mode-600 backup, rolls back failed candidates,
  tries at most two, and restores the original after an interrupted attempt. It
  probes the secure runner before repair and always executes candidates through
  Agent 4.3's Bubblewrap runner. The fixture test used actual
  Bubblewrap execution for the failed and successful candidates. The test candidate
  strings were deterministic fixtures, **not** AI generated.
- In the standard Codex tool sandbox, Bubblewrap returned namespace permission
  denial. In an approved unrestricted diagnostic process, the corrected probe
  returned `SECURE_RUNNER_VERIFIED`: exit 0, host home hidden, separate network
  namespace. This proves that specific Bubblewrap configuration works outside the
  Codex tool sandbox. It does not prove a networked Codex model process is confined.
- Existing read-only `_db_sample()` returned `SCHEMA_VERIFIED_READ_ONLY_BOUNDED`
  with a 5-second statement timeout and 20-row limits. The sampled 20 historical
  price rows lacked `market`; 20 recent rates rows lacked both `released_at` and
  `vintage_date`. No schema write was attempted. PIT validation remains blocked.
- A new real local-snapshot Universal run completed its three exploratory domains:
  state `.universal_private/core_recovery_20261107/autonomous_state.json`, checkpoint
  24, `official_claim=false`. Rerun processed 0 domains and retained checkpoint 24.
  All three results remain `EXPLORATORY_ONLY`.
- Universal tests: 65 passed in the normal tool sandbox. Regime190 tests: 50 passed
  with the original hash-bound Naver snapshots copied into this worktree's ignored
  data directory. The seven targeted Self-Repair tests passed in the approved
  unrestricted process; one of those used real Bubblewrap. The ordinary sandbox
  skips that one test because Bubblewrap is unavailable there. Python compilation
  and `git diff --check` passed.

## PART 2 fault injection evidence

| Fault | Evidence | Status |
| --- | --- | --- |
| Code error, candidate rollback, alternative success | `test_generated_script_repair_in_real_bubblewrap` | REAL_SANDBOX_FIXTURE_VERIFIED; AI candidate generation unconnected |
| API 429 | `test_api_429_retries_once_then_recovers` | MOCK_INTEGRATED; no live provider 429 generated |
| GitHub DNS | `test_dns_failure_keeps_independent_research_running` | MOCK_INTEGRATED; no live DNS outage generated |
| GitHub 403 | `test_http_403_waits_without_retry_or_secret_in_state` | MOCK_INTEGRATED; no live 403 generated |
| DB column mismatch | contextual classifier fixture; real read-only schema sample | PARTIALLY_IMPLEMENTED; no automatic adapter rewrite |
| Bubblewrap permission error | real failed probe inside tool sandbox; real passed probe outside | ENVIRONMENT_DEPENDENT; no policy relaxation |
| Regression after generated repair | first candidate fails isolated verifier, backup restored, second succeeds | REAL_SANDBOX_FIXTURE_VERIFIED; full repository regression not run per candidate |
| Process interruption | `test_interrupted_repair_restores_original_on_resume`; supervisor crash tests | MOCK_INTEGRATED; durable backup and checkpoint behavior verified |

## Remaining work and gates

The end-to-end path is **not** `END_TO_END_VERIFIED`. Universal still lacks a
confined actual AI/Codex hypothesis and code generation call, a general data/PIT
adapter, AI candidate supply to Self-Repair, automated DB adapter correction,
and a complete model-to-backtest-to-repair-to-resume run. Agent 4.3's older
three Codex calls do not count as Universal execution. No new independent
holdout or release/vintage evidence was acquired. No investment performance
improvement, PIT approval or production readiness is claimed.

OpenAI's [non-interactive Codex documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
supports `codex exec --output-schema` and read-only mode, but also warns that
saved CLI authentication is sensitive. The existing Agent 4.3 `_codex` passes
the host HOME and does not confine the Codex process's read paths at OS level.
It was therefore not wired into a broader unattended Universal run here.

Next: isolate the Codex caller with a minimal credential boundary and explicit
research input mounts; connect structured hypotheses and validated code to a
generic stage contract; run one real goal through the entire path; add a read-only
DB schema adapter repair fixture and live provider error handling; acquire PIT
release/vintage evidence and an unexamined holdout before official validation.

## Reproduction and next-session checkpoint

Working tree: `/home/kegor2/market-morning-reports-core-recovery`. Python:
`/home/kegor2/stock_env/bin/python`. The private state directory is ignored by
Git. The verified exploratory execution and resume command is:

```bash
cd /home/kegor2/market-morning-reports-core-recovery
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.autonomous --goal '한국 증시 급락 위험과 차트 및 전략의 탐색 연구' --goal-id core-recovery-20261107 --snapshot market-history/research/daily-index-validation-20261021/naver_kospi_daily.csv --state-dir .universal_private/core_recovery_20261107 --max-cycles 3
```

The verified test commands are:

```bash
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -p 'test_*.py' -q
```

The read-only DB probe was run from this worktree through
`regime190.agent3_experiments._db_sample`. Running it requires the existing
read-only credential file and network permission. No service or deployment
command was run.

## 2026-11-08 continuation

- The existing uncommitted work was preserved. Universal tests passed (68), and
  Regime190 tests passed (50). A dependency failure in a backtest stage now
  classifies as `DEPENDENCY_ERROR` rather than a generic backtest failure.
- The isolated Codex path now probes Bubblewrap before recording a model call.
  A denied namespace leaves `codex_calls=0`, allowing a later authorized host
  retry without a duplicate-call ambiguity. Invalid structured responses are
  recorded as blocked instead of escaping after the call, and successful calls
  no longer persist the model's stderr response text as a diagnostic.
- The ordinary tool sandbox probe was `SECURE_RUNNER_UNAVAILABLE` (seccomp 2,
  AppArmor `bwrap//&unpriv_bwrap`, no effective capabilities). The approved host
  probe was `SECURE_RUNNER_VERIFIED` (exit 0, home hidden, separate network
  namespace). Neither policy was changed.
- One real isolated Codex call generated a schema-valid hypothesis for Korean
  crash risk: model `gpt-6-sol`, UTC `2026-11-08T14:51:53.145072+00:00`,
  prompt SHA-256 `a830e7fb0f12840650cfdfe55a640415d551a6eab10e009a2d8543a169707fa0`,
  response SHA-256 `03b0c674b3e5392f96c4600c2f9cb3e3549511c4ff9a2d36f336d4bcee25e518`.
  Private state: `.universal_private/continuation_20261108_ai`. The hypothesis
  requires historical foreign-investor flows, FX and publication/vintage evidence.
- Universal checkpoint 24 completed three **template-generated exploratory**
  calculations over the supplied local KOSPI snapshot. A resume processed zero
  domains and reused the recorded AI response. Those calculations do not test
  the new AI hypothesis; generated research code and a matching backtest remain
  unconnected. `END_TO_END_VERIFIED` is therefore false.
- The approved read-only DB sample again returned
  `SCHEMA_VERIFIED_READ_ONLY_BOUNDED`: 20/20 historical price rows lack `market`;
  20/20 recent rates rows lack `released_at` and `vintage_date`. These are data
  values, not absent schema columns. PIT remains unverified. No DB write occurred.

Next priority: connect the AI hypothesis to a constrained data contract and Agent
4.3 code generator, then verify code and one matching backtest in the working
Bubblewrap context. Acquire publication/vintage evidence before any PIT or
investment-performance claim. The local state is a resume checkpoint; the
source worktree must be committed separately after final regression checks.

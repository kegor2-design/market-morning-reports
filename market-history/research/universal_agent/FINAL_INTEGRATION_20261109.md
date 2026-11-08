# Universal Agent final integration checkpoint — 2026-11-09 KST

## Verdict and source

Branch: `research/autonomous-core-recovery-20261107`, base commit
`2b1bcebdc3fc337b827bb7676a28ad8e87ef803f`. This work reused Agent 2.0,
the Universal supervisor/checkpoint engine, Agent 3/4.1/4.2 research evidence,
Agent 4.3 staging, code schema, static gate, Bubblewrap runner and backtest
verifier. No operating branch, DB row/schema, trading setting, service or cron
was changed. The previous [guided evidence](PART1_GUIDED_EVIDENCE_20261109.md)
remains the baseline.

| Capability | Current status | Evidence |
| --- | --- | --- |
| Real AI goal/hypothesis | VERIFIED | `gpt-6-sol` hypothesis response SHA-256 `dab85a33c500829b570bbbe3ab632fc34b9dca6a85280c94ef68e620e8e7b8a7`. |
| Real AI plan | VERIFIED_AFTER_REPAIR | Initial actual plan proposed unsupported logistic regression and percentage splits; adapter rejected it. A second real model call produced a compatible two-fold frequency plan, response SHA-256 `0d649986ce32c62d93ddea159919500071aa52fea90a50c81805b74b2cf1a671`. |
| Plan consumed by Agent 4.3 code generation | VERIFIED | Fresh `plan_first_crash_20261109` run passed the verified plan in the Agent 4.3 brief. New real code call: model `gpt-6-sol`, prompt SHA-256 `d7b027a7cdcac2ecf5ef98e61f4bf26d26f8e6463f9f852c8c79520e5b24a525`, response SHA-256 `7a2f25a87d3127ac6c76b3551879f68fd0ff2b3396c753f2ea090d1e969007d6`, code SHA-256 `45b3d14aa7b1cf1410106cefd182f36d1e6cfc6afae3997d774f2c6c31089be9`. |
| Generated code security | VERIFIED_FOR_THIS_RUN | Agent 4.3 schema/AST gate, allowable imports, Bubblewrap no home/network, read-only source/data bind, 15-second CPU, 256 MiB address space, 10 MiB file, 32 file descriptors and 32-process limit. Input write probe failed with read-only filesystem and unchanged hash. CPU loop stopped at the 15-second limit as `EXEC_TIMEOUT`; no child remained. |
| Real AI code repair | VERIFIED_FOR_INJECTED_FAULT | `guided_auto_repair_trial_v2_20261109` injected an allowed-library call error into a copy of a real AI artifact. Guided execution diagnosed `CODE_ERROR`, applied the separately real AI repair candidate `d0d6951449c49a27e850993208e088649fda97867eab3eb6af9321b47488c895`, verified output contract in Bubblewrap, resumed both folds, and restored the checkpoint without a new model call. A spontaneous model defect was not observed. |
| Rollback and alternative | VERIFIED_FOR_INJECTED_REGRESSION | Prior `fault_trial/fault_evidence.json`: first AI-generated candidate failed an injected regression gate and rolled back; second real AI repair candidate passed. |
| Fault classification | VERIFIED_INJECTION | Actual AI source copies: column mismatch `SCHEMA_MISMATCH`, leaked validation target `DATA_CONTRACT_ERROR`, output column defect `OUTPUT_CONTRACT_ERROR`, allowed-library call `CODE_ERROR`, missing input `DATA_GAP`. Repeated `CODE_ERROR` moved from repair to `SAFE_BLOCKED`. Model auth/rate/DNS/timeout categories are unit-tested, not live provider failures. |
| Checkpoint/STOP/duplicate prevention | VERIFIED_WITH_LIMIT | Live guided replay processed no duplicate fold or model call and checks source/input/output hashes. Separate Universal exploratory work completed three independent domains while PIT was blocked, then replayed zero tasks. AI call files now use atomic mode-600 exclusive reservations and a six-call state budget. A forced OS kill during the latest live model call was not performed. |
| Real backtest | EXPLORATORY_VERIFIED | New plan-first code ran in two sealed historical folds, 720 validation rows (2012–2014) and 717 (2015–2017), with 20-session embargo. Fold 1 PR-AUC `0.014245` versus volatility-only `0.016667`; top-decile event rate `0` versus overall `0.016667`. Fold 2 PR-AUC `0.024000` versus `0.023952`; top-decile `0.013889` versus overall `0.005579`. The AI hypothesis is `REJECTED_EXPLORATORY` because fold 1 failed the predeclared criterion. This is a research result, not a software failure. |
| PIT and independent validation | BLOCKED | Historical publication/vintage timing unverified and no unexamined holdout. Regime190's prior 190-indicator audit lists zero PIT-verified indicators. No official predictive or trading-performance claim. |
| AI next action | VERIFIED_WITH_POLICY_GATE | A new real `gpt-6-sol` result-evaluation call selected `PIT_VALIDATION_REQUIRED`, response SHA-256 `7f70caa94133bc15f8d02382356e5a855a0ca39a704c7909743b0ce91f48061b`. Host policy forbids model-declared completion, automatic PIT/data authorization, and treating poor hypothesis performance as a code fault. |
| Generality | PARTIAL | Common diagnosis, model-call, checkpoint and execution contracts are reusable. The only live guided data adapter supports Regime190 crash20 with five lagged features. Other user goals are classified `DATA_ACQUISITION_REQUIRED` and checkpointed rather than silently mapped to this experiment. |

## Read-only data evidence and limits

The existing Regime190 snapshot manifest identifies Naver Finance KOSPI/KOSDAQ
daily snapshots, historical range 1996-01-03 to 2026-10-20 for KOSPI and
1996-07-02 to 2026-10-20 for KOSDAQ, with source hashes in the private guided
state. Publication timestamp status is `UNVERIFIED`; prior periods have already
been inspected. The Agent 4.3 staging code seals validation labels outside the
generated-code mount and applies its chronological embargo.

The current read-only PostgreSQL inspection queried `information_schema` for
the three tables used by the existing Regime190 probe. Observed columns include
`domestic_daily_price.market_date` (`date`), `market` (`text`), `available_at`
(`timestamp`); `domestic_index_daily.market_date` (`date`), `index_code`
(`text`), `available_at` (`timestamp`); and `market_rates_snapshot.data_date`
(`date`), `released_at` (`timestamp`), `available_at` (`timestamp`),
`vintage_date` (`date`). These columns exist. In bounded 20-row samples,
historical `market` values were missing 20/20 and recent rates `released_at`
and `vintage_date` values were missing 20/20. The DB probe used `BEGIN READ
ONLY`, a five-second statement timeout and no write.

Existing source discovery reports show bounded FRED/ECOS/DART access, but do
not establish the release-hour, full-period vintage, rights and independent
holdout evidence needed here. KRX/KIS authenticated historical coverage was
not proven. Provider access and PIT approval remain separate decisions.

## Private evidence and reproducible commands

Model requests/responses are mode-600 and ignored by Git under
`.universal_private/plan_first_crash_20261109`. The execution checkpoint is
`market-history/research/.universal_private/plan_first_crash_20261109/guided_state.json`.
The integrated fault evidence is
`market-history/research/.universal_private/guided_auto_repair_trial_v2_20261109/integrated_fault_evidence.json`.
The data/output fault evidence is
`market-history/research/.universal_private/guided_crash_20261109/faults/fault_evidence.json`.
None is committed or pushed.

The following commands were run in this worktree. Host Bubblewrap and DB
commands required the approved host context; the ordinary Codex tool sandbox
cannot create Bubblewrap namespaces.

```bash
cd /home/kegor2/market-morning-reports-core-recovery
/home/kegor2/stock_env/bin/python --version
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -c 'from regime190.agent3_experiments import _db_sample; import json; print(json.dumps(_db_sample()))'
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.guided_experiment --ai-state-dir .universal_private/plan_first_crash_20261109 --state-dir market-history/research/.universal_private/plan_first_crash_20261109 --ai-next-action
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python market-history/research/universal_agent/tests/manual_guided_auto_repair.py --ai-state-dir .universal_private/guided_crash_20261109 --state-dir market-history/research/.universal_private/guided_auto_repair_trial_v2_20261109
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python market-history/research/universal_agent/tests/manual_guided_faults.py --state-dir market-history/research/.universal_private/guided_crash_20261109
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m compileall -q market-history/research/universal_agent market-history/research/regime190/agent43_engine.py
git diff --check
```

Final host regression: 81 Universal tests and 51 Regime190 tests passed,
including the real Bubblewrap fixture. No chmod or service registration was
needed. The next autonomous dependency is PIT release/vintage evidence and a
fresh independent evaluation period. That dependency may require source rights
review; it cannot be solved by changing the security policy or the operating DB.

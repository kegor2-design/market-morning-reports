# PART 1 guided AI experiment evidence, 2026-11-09 KST

## Verdict

| Completion gate | Result | Evidence and limit |
| --- | --- | --- |
| `REAL_CODE_GENERATION_VERIFIED` | PASS | Real `gpt-6-sol` hypothesis was passed to Agent 4.3's guided prompt/schema/static gate; a second real call generated a repair candidate. Both artifacts are hash-bound in the private AI checkpoint. |
| `REAL_SELF_REPAIR_VERIFIED` | PARTIAL | A syntax error was **injected into a copy** of actual AI-generated code. The first AI-generated candidate was rejected by an injected regression gate and rolled back; the second, real AI repair candidate passed Bubblewrap and the output contract. The production guided run did not encounter a spontaneous model code error. Data-adapter auto repair was not demonstrated. |
| `SECURE_BACKTEST_VERIFIED` | BLOCKED | The original and repaired code both executed in Bubblewrap over real historical snapshots, but publication/vintage evidence and an independent holdout are unavailable. These are exploratory backtests, not PIT-verified performance tests. |
| `PART_1_COMPLETED` | NO | All three gates need PASS. |

## Existing implementation reused

- Agent 2.0 objective/contract and Universal checkpoint/lock machinery remain in their existing modules.
- Agent 4.3 supplied `_prompt`, its JSON schema, `_check_code`, `_stage_market`,
  `_isolated_python`, and `_verify_market`. The guided branch of `_prompt` is
  selected only when an external AI hypothesis is supplied; prior prompts keep
  their existing behavior. Its source hash changed, so previously prepared
  Agent 4.3 queues must use their existing code-revision review path before replay.
- `isolated_codex.call_structured` confines model calls; `self_repair` classifies
  faults, bounds plans, applies candidate code only in a research tree, and rolls
  back failed verification. Generated code sees only a staged fold directory in
  Bubblewrap, not the sealed labels, host home, network, DB credentials, or trading
  APIs. CPU, memory, file size and wall-time limits come from Agent 4.3.
- `guided_experiment` is a small adapter for the existing Regime190 crash20
  contract, not a new general agent. Unsupported data requirements block before
  staging. The model process, generated-code process and durable state are separate.

## Real calls, data, execution

- Real hypothesis: `gpt-6-sol`, UTC `2026-11-08T15:01:04.996790+00:00`;
  prompt SHA-256 `a168a79cd598fdbf89ab1ebf4c113091f8fe44fd8f38b884c61c7bc657e7abe6`;
  response SHA-256 `dab85a33c500829b570bbbe3ab632fc34b9dca6a85280c94ef68e620e8e7b8a7`.
  The hypothesis uses five lagged KOSPI/KOSDAQ features to predict the existing
  20-session crash label. Its rejection condition calls for comparison with a
  volatility-only baseline; the existing Agent 4.3 verifier instead compares
  with its frozen drawdown baseline. The specific rejection condition is therefore
  **not independently resolved** by these results.
- Real initial code: `gpt-6-sol`, UTC `2026-11-08T15:05:29.929501+00:00`;
  response SHA-256 `aced64ff69b789bc8cfb937bb27941f01a34bf1f4a4ae77b006c4abe4363c27c`;
  code SHA-256 `b1acd74fd4ad91ea171bf3c88c6248befba402358469e515f97233c796bdb92c`.
  JSON Schema and Python AST/static checks passed before execution.
- Real repair candidate: `gpt-6-sol`, UTC `2026-11-08T15:09:24.976040+00:00`;
  response SHA-256 `21c5c666ee3106131275a954c117327460d4d6e2e6f0cb468ee33ab2dd44b1ee`;
  repaired code SHA-256 `d0d6951449c49a27e850993208e088649fda97867eab3eb6af9321b47488c895`.
- Data: hash-bound Naver Finance KOSPI/KOSDAQ daily snapshots, 1996-01-03 to
  2026-10-20 and 1996-07-02 to 2026-10-20 respectively. Agent 4.3 staged two
  chronological folds with 20-session embargo and validation labels sealed
  outside the generated-code mount. Validation: 720 rows in 2012-2014, 717 rows
  in 2015-2017. Historical publication timestamps are unverified; prior work
  inspected these periods, so no independent holdout remains.
- Original code, fold 1: PR-AUC 0.01425, precision 0, recall 0, false-alarm
  rate 0.15113, Brier 0.02075 versus frozen baseline 0.02144. Fold 2: PR-AUC
  0.02400, precision 0, recall 0, false-alarm rate 0.07854, Brier 0.00761
  versus baseline 0.00862. The repaired code also passed both folds, with
  PR-AUC 0.01220 and 0.01539; precision and recall remain 0 at the fixed
  threshold. This is risk classification, not a traded strategy; taxes,
  slippage, liquidity and portfolio drawdown do not apply to this run.
- The real read-only PostgreSQL probe returned
  `SCHEMA_VERIFIED_READ_ONLY_BOUNDED`, 20-row limits and a 5-second statement
  timeout. Actual columns were read via `information_schema`. In sampled rows,
  historical price `market` is missing 20/20; recent rates `released_at` and
  `vintage_date` are missing 20/20. Those are missing **values**, not columns.
  The DB schema and rows were not changed.

## Faults, recovery and resume

| Fault | Real execution result | Recovery result |
| --- | --- | --- |
| Injected syntax error in copy of AI code | Source SHA-256 `2bd473ff5bbd73ffff3f3517178856896eff1d820159ceb03b326eb1abb3bdd2` | First AI code candidate rolled back after injected regression rejection; second real AI repair candidate verified in Bubblewrap. |
| Column mismatch | Bubblewrap exit 1 | `SCHEMA_MISMATCH`, `INSPECT_READ_ONLY_SCHEMA`; no automatic adapter rewrite claimed. |
| Validation target leak | Bubblewrap exit 1 | `DATA_CONTRACT_ERROR`, `INSPECT_INPUT_CONTRACT`. |
| Allowed-library call error | Bubblewrap exit 1 | `CODE_ERROR`, `REPAIR_RESEARCH_CODE`. |
| Same error repeated | Two contextual diagnoses | First `REPAIR_RESEARCH_CODE`, then `SAFE_BLOCKED`; no infinite retry. |
| Interrupt and resume | Existing interruption test plus live checkpoint replay | Durable backup recovery test passed; live guided replay reported `resumed_without_duplicate=true` and used stored output hashes. No forced OS kill of this specific live process was performed. |

Private evidence paths relative to this worktree:

- `.universal_private/guided_crash_20261109/ai_request.json`, `ai_response.json`,
  `code_initial_request.json`, `code_initial.json`, `code_repair_request.json`,
  `code_repair.json`.
- `market-history/research/.universal_private/guided_crash_20261109/guided_state.json`,
  `fault_trial/fault_evidence.json`, `faults/fault_evidence.json`, and
  `repaired_backtest/evidence.json`.

The ordinary Codex tool sandbox denied Bubblewrap namespace creation. An
approved host process on Linux 6.8, user `kegor2`, reported user namespace
enabled, seccomp 0, AppArmor unconfined, zero effective capabilities, host home
hidden and separate network namespace. No security policy was changed.

## Regression and next priority

Universal tests: 73 passed. Regime190 tests: 50 passed. The Self-Repair subset
passed 8 tests in the host Bubblewrap context. Python compilation and
`git diff --check` passed. No operating code, DB schema/rows, service, trading
setting or deployment was changed.

Next: acquire time-stamped, vintage-aware PIT evidence and an unexamined
evaluation period; implement the AI hypothesis's own frozen volatility-only
comparison and high-risk decile metric; demonstrate autonomous adapter repair
for missing columns; then repeat the complete path before moving to PART 2.

## Commands executed in this worktree

The following were executed; no chmod was needed because Python scripts were
invoked through the interpreter. `cd` and the virtualenv check are ordinary
preflight steps; the state paths below are deliberately private.

```bash
cd /home/kegor2/market-morning-reports-core-recovery
/home/kegor2/stock_env/bin/python --version
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -c 'from regime190.agent3_experiments import _db_sample; import json; print(json.dumps(_db_sample()))'
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m compileall -q market-history/research/universal_agent market-history/research/regime190/agent43_engine.py
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -c 'from universal_agent.self_repair import probe_secure_runner; import json; print(json.dumps(probe_secure_runner()))'
mkdir -p .universal_private/guided_crash_20261109
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -c 'from pathlib import Path; import json; from universal_agent.isolated_codex import generate; goal="한국 주식시장의 20거래일 급락 위험을 사전에 탐지하라. 사용 가능한 연구 입력은 KOSPI/KOSDAQ 일별 종가에서 과거 시점만으로 계산한 momentum5, momentum20, volatility20, drawdown60, relative_kosdaq20과 훈련 구간의 crash 이진 라벨이다. 외국인 수급, 환율, 거시 지표는 이 실험에서 사용할 수 없다. 이 입력만 사용해 가설을 제시하고 PIT 및 독립 평가 데이터가 부족함을 명시하라."; result=generate(goal,Path(".universal_private/guided_crash_20261109")); print(json.dumps({k:v for k,v in result.items() if k!="hypothesis"},ensure_ascii=False)); print(json.dumps(result.get("hypothesis"),ensure_ascii=False))'
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.guided_experiment --ai-state-dir .universal_private/guided_crash_20261109 --state-dir market-history/research/.universal_private/guided_crash_20261109
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python market-history/research/universal_agent/tests/manual_guided_faults.py --state-dir market-history/research/.universal_private/guided_crash_20261109
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python market-history/research/universal_agent/tests/manual_guided_repair_backtest.py --ai-state-dir .universal_private/guided_crash_20261109 --state-dir market-history/research/.universal_private/guided_crash_20261109
```

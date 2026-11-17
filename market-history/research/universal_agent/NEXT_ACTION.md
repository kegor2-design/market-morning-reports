# Next research actions

## Session C development handoff — 2026-11-17

- Branch: `research/universal-agent-session-c-20261117`; last verified code commit: `f22df0f` (based on Session B `cea23c0070c445c402f1def51e324ddbb03a1a13`).
- Phase: C1 partial. The bounded Goal queue, queue-specific checkpoints, terminal deduplication, approval blocking, and detached shell-exit execution have been implemented. The remaining P0 fault matrix and actual SSH disconnect are not complete. No worker was still running at this checkpoint.
- Tests: Universal Agent 131 PASS under server user execution; Regime190 55 PASS; compileall and diff check PASS. The sandboxed Universal Agent run had three Worker-start failures; rerunning outside that process sandbox passed all 131.
- Private checkpoints: `.universal_private/session_c_disconnect_2/state.json`, `.universal_private/session_c_rates_may2018/state.json`, `.universal_private/session_c_rates_june2018/state.json`. The June Goal finished exploratory; May remains blocked on market-day coverage; indicator 116 remains PIT blocked.
- Pending: P0 kill, network, time, model, disk, checkpoint, SSH disconnect tests on the new queue; P1 reviewed AI planner; P2 market calendar and official KRX; P3 solver/repair DAG integration; P4/P5 independent holdout and new A/C/D goals. The existing isolated Codex runner passed its secure-runner probe outside the process sandbox, but no Session C planner model call was made. KRX official access remains unavailable with the tested unauthenticated endpoint.
- Required approval: no approval to read or develop in the research worktree. A real independent service installation or scheduler change would require separate approval. Source/API costs and access must be reviewed before enabling new providers.

Verified resume commands (the Python environment and paths were checked on this host):

```bash
cd /home/kegor2/market-morning-reports-session-c
git fetch origin research/universal-agent-session-c-20261117
git status --short --branch
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.research_runtime status --queue-dir .universal_private/session_c_rates_june2018
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
```

Run process-kill tests in the approved server user execution environment; the restricted process sandbox prevents their workers from starting. Review the Session C reports and continue with the P0 fault matrix before promoting any gate.

## Session B handoff

1. Add a reviewed AI planning path with strict host validation, an explicit model-call budget, and an approved provider. The present planner is deterministic and supports only three narrow families.
2. Add official KRX series and a market calendar after source terms and access are approved. The current Korean crash study is exploratory and its local Naver CSVs are intentionally untracked. Restore only files matching the SHA-256 values in `daily-index-validation-20261021/naver_source_manifest.json` before reproducing it.
3. Acquire historical first-publication, first-access, and revision evidence for indicator 116 and the rate series. PIT-blocked goals must remain blocked until then.
4. Exercise an interrupted live provider call only in an approved, bounded research environment. Local HTTP tests prove the fail-closed and sealed-response paths, not provider-specific behavior.
5. Integrate additional Problem Solver outcomes and isolated AI Self Repair into the program DAG without changing production code. Validate long-running operation, paid-call budgets, and operational impact before deployment.

Resume the reviewed private goals from the follow-up worktree with the existing virtual environment:

```bash
cd /home/kegor2/market-morning-reports-session-b-completion
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.process_supervisor --research-goal '지표 116의 한국 증시 PIT를 검증하고 차단되면 독립적인 미국 국채 금리차와 SOFR 연구를 수행하라.' --max-seconds 180
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
```

The second command needs local loopback socket permission for the HTTP interruption tests. Both existing research programs are checkpointed; resuming them should not repeat completed source requests.

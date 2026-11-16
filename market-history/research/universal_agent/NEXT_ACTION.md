# Next research actions

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

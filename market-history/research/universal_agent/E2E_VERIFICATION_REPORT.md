# End-to-end verification — 2026-11-14

| Check | Status | Evidence |
| --- | --- | --- |
| Compile changed agent modules | PASS | `python -m compileall -q market-history/research/universal_agent` |
| Universal Agent regression | PASS with one SKIP | 105 tests; Bubblewrap environment test skipped |
| Regime190 regression | PASS | 55 tests after restoring two ignored, hash-checked CSV fixtures from basis worktree |
| New acquisition, mismatch, HTTP and interruption unit tests | PASS | 6 tests in `test_data_recovery.py` |
| Actual official data collection | PASS | Treasury CSV SHA-256 `a9278f347b48b819d68f91961e3e1a18431514ae3763ef888cc9f1bdb064b254`; 10Y `1.92`, 2Y `0.55` recovered |
| Research Job / Supervisor integration | PASS | `treasury_job_live` one Worker attempt, result `DATA_RECOVERED_PIT_UNVERIFIED`, Supervisor `RESEARCH_BLOCKED_WITH_EVIDENCE` |
| Independent source/value recomputation | PASS | `verify_recovery` and Supervisor artifact verifier, including terminal rerun with unchanged attempt count |
| Actual mismatch detection | PASS | `187` versus `1.87` preserved and classified `DATA_MISMATCH` |
| PIT evidence insufficiency / next task | PASS for blocked gate and fixture transition | Indicator 116 evidence SHA-256 `2d88127004f5fda9128cd95658d433ebbd161b336d7c070c15566fd91b4a3d52`; `PIT_BLOCKED`; independent fixture only |
| Live automatic code fix and rollback | BLOCKED | Bubblewrap namespace creation denied; no new experiment performed |
| New networked Worker and Supervisor forced-kill/resume | PASS for sealed output | Live SIGKILL probes; both resumed with one Worker attempt and one official request; no duplicate completion |
| `git diff --check` | PASS | No whitespace errors |
| Production readiness, PIT verified, investment result | BLOCKED | Historical source access clocks and independent market holdout absent |

Private job checkpoint SHA-256 (at report generation): `11f49e3f45d5fcf13287282d3f6e4bfb5820ea4e36fa6c6fdd8ee5c0a57a5e00`. Private workflow checkpoint SHA-256: `20afef8c9f47548101e2391ca3aca33f4494957423f6501779d7bc63ed97dace`. Private paths contain raw bytes and are deliberately ignored by Git. Model calls: zero. No operating DB query was needed for these Treasury runs.

Resume and independent verification from this worktree:

```bash
cd /home/kegor2/market-morning-reports-autonomous-data-recovery
chmod 600 .universal_private/autonomous_data_recovery/job_manifest.json
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.process_supervisor --research-manifest .universal_private/autonomous_data_recovery/job_manifest.json --job-dir .universal_private/autonomous_data_recovery/treasury_job_live
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
```

The first command reuses the terminal checkpoint; it does not download again. A new collection requires a new reviewed manifest and task ID. No new executable script was added, so `chmod +x` is not needed.

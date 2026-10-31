# Regime190 evidence discovery handoff — 2026-11-01 KST

## Starting state and preservation

Starting branch `research/regime190-data-audit-20261027`, commit
`0c08f206a7a5b4c2f2a659d9bb224040397e9516`; local and remote HEAD matched
and the tree was clean. The private production queue had checkpoint 3, a valid
SHA-256, three completed d0 tasks, six pending d1/d2 tasks and one
`CODEX_REQUIRED` cutoff task. The 02:15 KST cron entry remains installed and
was not edited. Existing Phase 4/5 supervisor, Runner, worker plan, cron wrapper,
production checkpoints, trading code and database schema were not changed.

## IMPLEMENTED

The new `blocker_resolution.py` reads four 190-row audit files and the private
SQLite checkpoint in read-only mode. It records required fields, current data,
missing evidence, primary and secondary blocker classes, resolution action,
alternative-source text, priority, execution class and PIT validation needs for
every indicator. The existing offline worker now accepts allowlisted
`source_catalog_probe` and `blocker_classify` tasks. The probe sends at most
six HEAD requests to official documentation addresses, records status metadata
and does not follow redirects. Classification records its artifact hash and
creates at most 12 idempotent local checks from
distinct checkpoint artifact references. The current data yielded two distinct
references. A crash during classification verification restores generated tasks
from the persisted artifact. The production plan is unchanged.

The local check validates the price manifest's 2,497 unique file names and one
matching checksum sample, or validates the short-history rates artifact against
its manifest. It never sets PIT approval. Existing FRED collection and Phase 4/5
components were retained; no new provider data collector was enabled because
source-specific rights, row coverage and release timing remain unverified.

## EXECUTED and VERIFIED

The final isolated run at
`~/MyDream2000/research/universal_agent/regime190-evidence-discovery-live-v1`
completed source probing, classification and two generated checks in about two
seconds, checkpoint 4. Queue/checkpoint SHA-256 matched. A second bounded run processed
zero tasks. Every completed task had one attempt. The price manifest sample
matched and ID 51 had 4,547,612 declared valid rows across 2,497 unique files.
The rates manifest/file checksum matched and ID 107 had 325 rows from
2025-07-01 to 2026-10-28. These are existing derived evidence, not newly
retrieved observations or verified publication-time data.

Primary blockers: `MISSING_SOURCE` 98, `MISSING_TIMESTAMP` 92. Multi-label
gaps: missing timestamp 190, historical universe 190, revision history 190,
calculation validation 190, source 98 and corporate-action policy 4. The
prior PIT classes remain 71 `PIT_BLOCKED`, 21 `CALCULATION_PENDING`, 98
`SOURCE_MISSING`, zero `PIT_VERIFIED`. Newly resolved PIT blockers: **0**.
PIT approved indicators: **0**. Historical backtest: **BLOCKED and not run**.

## Source investigation

The [source catalogue](source_discovery_20261101.json) records endpoint or
documentation status, historical coverage uncertainty, publication timing,
revision and licensing status, and candidate indicator families for KRX, BOK
ECOS, KOSIS, FRED, OpenDART and KIS. Bounded unauthenticated checks reached the
KRX, ECOS, KOSIS and KIS documentation pages (HTTP 200), FRED observations
endpoint (HTTP 400 without an API key), and OpenDART list endpoint (redirected
to an error page without a key). This verifies reachability only; it does not
verify authenticated row-level access or historical coverage. FRED documents
real-time vintages; its observation date is not the release hour. KIS market
data has account-use and redistribution limits. The autonomous HEAD pass
returned KRX 403, ECOS 200, KOSIS 200, FRED documentation 200, OpenDART 302
and KIS 200. KRX differed from the earlier curl check, so client-specific
access remains unresolved. All six collection flags stay off pending
indicator-specific checks.

Official references: [KRX service list](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd),
[KOSIS OpenAPI](https://kosis.kr/serviceInfo/openAPIGuide.do),
[FRED observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html),
[FRED terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html),
[OpenDART list](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001),
[KIS API](https://apiportal.koreainvestment.com/apiservice-summary),
[KIS use scope](https://apiportal.koreainvestment.com/about-open-api).

## TESTED and production safety

Baseline: 45 common and 10 Regime190 tests passed in their supported Python
environments. Final: 47 common and 13 Regime190 tests passed; Python compile
and `git diff --check` passed. A recovery iteration defect surfaced in a new
test and a probe verification routing defect surfaced in the first isolated
run; both were fixed and the full flow was rerun. Host preflight: two vCPUs,
about 2.8 GiB available memory and 47 GiB free disk. The bounded execution
used one worker, four tasks total and no production PostgreSQL query; its only
database access was the private SQLite checkpoint opened read only. No
permanent service, cron, credentials, trading code or production DB write was
introduced.

## BLOCKED and next autonomous tasks

`resolve_cutoff_origin` and `source_rights_review` are `CODEX_REQUIRED` in the
isolated queue. The original bulk request/response, historical universe,
row-level publication times, vintage/revision records, corporate-action
policies and independent calculation reference checks remain open. The next
autonomous plan should add a collector only after an official endpoint, exact
series, usage rights, historical coverage and release-time metadata are
verified for an indicator. It can then enqueue a bounded keyed fetch, preserve
raw evidence where permitted, deduplicate and validate the schema, and rerun
PIT classification. See [verification protocol](verification_protocol_20261101.md)
for calculation tasks and walk-forward backtest gates. No automatic promotion
is allowed from an available API or calculation alone.

## Exact inspection and resume commands

```bash
cd /home/kegor2/market-morning-reports/market-history/research
/home/kegor2/stock_env/bin/python -m universal_agent.offline_worker status --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-evidence-discovery-live-v1 --repo /home/kegor2/market-morning-reports
/home/kegor2/stock_env/bin/python -m universal_agent.offline_worker run --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-evidence-discovery-live-v1 --repo /home/kegor2/market-morning-reports --max-tasks 5 --max-seconds 120
```

The second command currently processes zero tasks. Deploying another evidence
plan requires a new private state directory and separate review; the scheduled
production queue is deliberately not pointed at this plan.

# Regime190 첫 실데이터 연구 주기 — 2026-11-01

## 결론과 상태

**공식 PIT 적격 역사 백테스트는 실행되지 않았다 (`BLOCKED_PIT`).** 190개 지표 중 `PIT_VERIFIED=0`, 비공개 SQLite `pit_eligible=1`도 0개다. 과거 관측값은 있으나 발표·가용 시각, 개정 빈티지, 당시 종목군과 계산 검증이 부족하다. 이 조건을 우회하지 않았다.

**실데이터 탐색 파이프라인은 실행됐다 (`EXPLORATORY_REAL_DATA_PIT_UNVERIFIED`).** Naver KOSPI/KOSDAQ 보존 스냅샷으로 2010-03-31~2026-09-15의 4,052개 결정일에 6국면을 계산하고, 다음 공통 세션 시가로 체결하는 진단용 전략, 미래 결과 라벨, 평가, Agent 2.0 워커 큐·체크포인트·메모리·handoff를 완료했다. 이 수치는 공식 성과, PIT 검증 또는 투자 판단이 아니다. 모델 추론 상태는 `DETERMINISTIC_NON_AI`다.

| 완료 기준 | 상태 |
|---|---|
| ARCHITECTURE_COMPLETE | IMPLEMENTED, 기존 Agent 2.0 재사용 |
| PIPELINE_EXECUTED | EXECUTED, 실데이터 탐색 경로 |
| REAL_DATA_BACKTEST_COMPLETE | BLOCKED, 공식 PIT 적격 지표 0 |
| STATISTICAL_VALIDATION_COMPLETE | INCONCLUSIVE, 겹치는 라벨·독립 사건 부족 |
| OUT_OF_SAMPLE_VALIDATION_COMPLETE | BLOCKED, PIT 미검증 및 임계값 검증 부족 |
| RESEARCH_OBJECTIVE_COMPLETE | INCONCLUSIVE |

## 기준선 및 기능 보존 행렬

시작 저장소 `market-morning-reports`, 브랜치 `research/autonomous-agent-v2-architecture-20261101`, HEAD `2c7f79e82aa161a3530fb42824f318a0d86e8d47`, 작업 트리 깨끗함. 원격 관련 브랜치 HEAD를 확인하고 두 기준 테스트 집합을 먼저 실행했다: universal_agent 54/54, regime190 23/23. 별도의 개발 브랜치 `research/regime190-end-to-end-backtest-20261101`에서만 수정했다.

| 구성요소 | 현재 구현 | 검증 상태 | 재사용 | 부족한 능력 | 회귀 위험 |
|---|---|---|---|---|---|
| Agent 2.0 목표·가설·계획 | `agent2.py` v1 계약 | 기준 테스트 통과 | 목표/가설 검사 | 실제 AI 계획 | 낮음 |
| 영속 큐·오프라인 워커 | `offline_worker.py` | 기준 테스트 통과 | 새 allowlist 어댑터 추가 | 공식 PIT 도구 | 중간 |
| 체크포인트·복구·중복 방지 | 동일 워커 + `engine.py` | 기준·통합 테스트 통과 | 원자적 기록과 잠금 | 장기 장애 주입 | 낮음 |
| 영속 연구 메모리 | Agent 2.0 JSON 계약 | 기준·통합 테스트 통과 | 실험 요약·SHA·결정 저장 | 여러 가설 주기 | 중간 |
| Regime190 190 지표·PIT 감사 | 기존 매트릭스·private SQLite | 실제 조회 및 기존 테스트 | 기존 분류 유지 | 적격 지표 0 | 낮음 |
| 역사 평가 원시 함수 | `historical_evaluation.py` | 기존 테스트 통과 | PIT gate, walk-forward 인덱스 | 공식 성과 입력 | 낮음 |
| 시장 데이터 | 보존된 KOSPI/KOSDAQ 지수 CSV | SHA 및 행 검사 | 탐색 입력만 | 발표 시각·빈티지 | 중간 |
| 실거래·MMP·cron | 별도 운영 체계 | 읽기 전용 확인 | 변경 없음 | 해당 없음 | 낮음 |

## 데이터 준비와 DB 스키마

현재 호스트는 2 vCPU, RAM 3.8 GiB(가용 약 3.0 GiB), 디스크 여유 47 GiB였다. Regime190 수집 프로세스가 실행 중이었고 02:15 KST `REGIME190_OFFLINE_RESEARCH` cron을 읽기 전용으로 확인했다. 둘 다 건드리지 않았다.

비공개 SQLite를 `mode=ro`, `PRAGMA query_only=ON`으로 조회했다. `tasks`와 `requests` 테이블, `tasks.indicator_id/pit_eligible/derived_series_path/...` 컬럼을 확인했고 `pit_eligible=1`은 0건이었다. PostgreSQL은 기존 전용 읽기 전용 자격증명으로 `BEGIN READ ONLY`, `SET LOCAL statement_timeout='5000ms'`를 적용해 `information_schema.columns`의 관련 8개 테이블 최대 200개 컬럼만 조회했다. `domestic_daily_price.market_date/close/market/available_at/collected_at`, `domestic_index_daily.market_date/index_code/close/available_at`, `market_rates_snapshot.released_at/available_at/vintage_date/revision_no` 등이 실제로 존재한다. 값이나 자격증명은 기록하지 않았다. 운영 데이터 테이블의 대량 집계는 수행하지 않았다.

| 데이터 | 이용 가능한 관측 범위 또는 기존 감사 | PIT/차단 |
|---|---|---|
| 보존 Naver KOSPI 지수 OHLCV | 1996-01-03~2026-10-20, 7,730행, 일별 | 발표 시각·수정 이력·공식 캘린더 미검증 |
| 보존 Naver KOSDAQ 지수 OHLCV | 1996-07-02~2026-10-20, 7,574행, 일별 | 위와 동일 |
| PostgreSQL 개별 종목 가격 | 기존 2026-10-28 감사: 2011-09-16~2026-10-27 약 460만 행 | 과거 `market` 대다수 공란, 조정·원본 시각 미검증 |
| 외국인 현물·시장 breadth | 기존 감사: 2025-04-16~, 2026-10-14~ | 짧은 구간, 당시 종목군·발표 시각 미검증 |
| 금리·외환·미국 시장 | 기존 감사: 금리 2025-07-01~, FX 2026-07-07~, 미국 2026-03-26~ | 빈티지/상품 매핑/가용 시각 미검증 |
| 외국인 선물·SOX·변동성·유동성 | 기존 매핑에 후보 또는 부분 원천 | 이 실험용 PIT 적격 시계열 없음 |

`TARGET_HISTORY` 약 30년. `AVAILABLE_HISTORY`의 가장 긴 지수 스냅샷은 약 30년이나 출처 시점은 현재 조회본이다. `PIT_ELIGIBLE_HISTORY` 0일. `BACKTESTED_HISTORY` 공식 0일, 별도 **탐색** 2010-03-31~2026-09-15이다. 전체 190개 메타데이터, 입력·빈도·결손·현재 분류·차단 사유는 비공개 [eligibility manifest](/home/kegor2/agent2_research_state/regime190_eligibility_20261101.json)에 생성했다. 보수적 상태는 `DATA_AVAILABLE` 84, `DATA_UNAVAILABLE` 106, `BACKTEST_ELIGIBLE` 0이다. 기존 PIT 분류는 `PIT_BLOCKED` 71, `CALCULATION_PENDING` 21, `SOURCE_MISSING` 98이며 자동 승격하지 않았다.

## 6국면 정의와 탐색 실행

결정 시각의 입력은 KOSPI 과거 60 공통 세션 종가와 KOSDAQ 과거 20 공통 세션 종가뿐이다. 20일·5일 모멘텀, 60일 고점 대비 하락, 20일 변동성, KOSDAQ 상대 수익을 순서 있는 고정 규칙으로 분류한다. 국면은 `RISK_ON_TREND`, `RISK_ON_SELECTIVE`, `CHOPPY`, `RISK_OFF_WEAK`, `RISK_OFF_PANIC`, `RECOVERY_EARLY`다. 파라미터는 `exploratory_v1_frozen_20261101`; 임계값은 초기 가설이며 학습된 규칙이 아니다. 신뢰도는 모멘텀 크기의 **비보정 휴리스틱**이며 확률이 아니다. 비가용 피처를 미래값으로 채우지 않았다.

일별 타임라인은 private 워커 아티팩트에 있다. 4,052일 중 `CHOPPY` 2,205, `RISK_ON_SELECTIVE` 685, `RISK_OFF_WEAK` 562, `RISK_ON_TREND` 452, `RECOVERY_EARLY` 38, `RISK_OFF_PANIC` 110일이다. 미래 수익으로 만든 충돌·회복 결과 라벨은 당일 포지션 입력과 별개다.

신호는 해당일 종가 후 계산했다고 **가정**하고, 다음 공통 세션 시가에 포지션을 잡아 그다음 공통 세션 시가까지의 수익을 측정한다. 한 방향 수수료 0.10%와 슬리피지 0.05%를 가정한다. 결측 거래일은 두 지수 공통 관측 세션만 사용하며, 독립 거래소 캘린더·체결 가능성은 미검증이다. 2010년 이전 OHLC 오류를 배제하고 60세션 warm-up과 20세션 결과 창을 확보했다.

## 탐색 진단 결과 — 공식 성과 아님

20세션 내 -10% 하락의 일별 경고: 정밀도 **7.59%**, 재현율 **24.29%**, 거짓 양성률 **16.16%**, TP 51/FP 621/FN 159. 겹치는 라벨 구간 26개 중 13개에서 라벨 시작일 이전 경고가 관측됐으나, 이 구간은 독립적으로 확인한 실제 폭락 사건이 아니다. 1·3·5·10·20세션의 전체 진단은 private 메모리에 있다.

회복 신호 38일 중 정의한 미래 회복 결과와 일치한 비율은 **5.26%**, 회복 결과일 대비 재현율 **2.25%**였다. 신호 13일은 이후 -5% 재하락해 탐색적 거짓 반등 비율 **34.21%**였다. 회복 확정·기회비용·재진입 적시성은 공식 검증되지 않았다.

동일 기간 진단에서 buy-and-hold 누적 수익률 **299.28%**, 최대 낙폭 **-43.08%**, Sharpe(무위험 0 가정) **0.530**; 6국면 노출 전략은 **34.93%**, **-34.08%**, **0.241**이었다. 6국면 가설이 이 탐색 설정에서 기준 전략보다 우수하다는 근거는 없다. 이동평균·변동성·경고 방어·회복 재진입 비교도 아티팩트에 기록했지만 PIT/체결 조건 미검증이므로 성과 주장에 사용하지 않는다.

`TRAIN` 2010~2017, `VALIDATION` 2018~2021, `FINAL_HOLDOUT` 2022~2026의 고정 날짜 요약과 1,000/252세션·20세션 embargo의 12개 시간순 fold 경계만 만들었다. 파라미터 학습·선택·독립 holdout 인증은 하지 않았다. 통계적·표본 외 유효성은 `INCONCLUSIVE`/`NOT_VALIDATED`다.

## Agent 2.0 통합, 재현성과 운영 안전

새 `regime190_exploratory` 어댑터는 기존 워커의 단일 `task_queue.json`과 allowlist, 잠금, 예산, 체크포인트를 사용한다. 목표/가설 계약을 Agent 2.0 함수로 검사한다. 평가 메모리에는 `EXECUTION_SUCCESS`, `DATA_VALIDITY`, `PIT_VALIDITY=BLOCKED`, `STATISTICAL_VALIDITY`, `OUT_OF_SAMPLE_VALIDITY`, `RESEARCH_VALUE=EXPLORATORY_ONLY`, `DEPLOYMENT_READINESS=NOT_READY`, `REQUIRE_PIT_EVIDENCE`, 원천 SHA, 코드 SHA, 파라미터와 아티팩트 SHA를 따로 기록한다. 재실행은 중복 평가 없이 `ALREADY_EVALUATED`; 아티팩트/입력/코드 변경은 오류로 차단한다. 모델 기반 가설 생성은 없다.

운영 PostgreSQL 읽기 전용 스키마 조회 외에 본 실험은 보존 CSV와 비공개 SQLite 읽기만 수행했다. MyDream2000 실거래, KIS 주문, MarketMorningPublisher, DB 스키마, 자격증명, cron, 실행 중인 서비스·체크포인트를 변경하지 않았다. 생성된 타임라인·메모리는 `/home/kegor2/agent2_research_state/`에 보관하고 Git에는 넣지 않는다.

## 다음 우선순위와 정확한 명령

1. 지수·선택 지표의 원본 발표 시각, 당시 가용 시각, 빈티지, 공식 거래일·종목군·상장폐지, 조정 정책과 라이선스 확인.
2. 독립 계산 대조와 row-level PIT manifest를 마련하고 기존 190개 분류를 검토 절차로 갱신.
3. 독립 폭락 사건 정의, 겹침 제거, 임계값 train/validation 선택, 표본 외 holdout 고정 후 공식 백테스트.
4. 미래 모델 런타임은 구조화 출력·비용 상한·정보 필터·감사 로그와 별도 승인이 필요하다. 현재 `NOT_ACTIVE`.

```bash
cd /home/kegor2/market-morning-reports-regime190-e2e
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
git diff --check

cd market-history/research
/home/kegor2/stock_env/bin/python -m regime190.eligibility_manifest --output /home/kegor2/agent2_research_state/regime190_eligibility_20261101.json
/home/kegor2/stock_env/bin/python -m regime190.research_cycle --mode official --state-dir /home/kegor2/agent2_research_state/regime190_exploratory_v4_20261101 --repo /home/kegor2/market-morning-reports-regime190-e2e
/home/kegor2/stock_env/bin/python -m regime190.research_cycle --mode exploratory --state-dir /home/kegor2/agent2_research_state/regime190_exploratory_v4_20261101 --repo /home/kegor2/market-morning-reports-regime190-e2e
```

마지막 명령의 동일 state-dir 재실행은 완료된 연구를 읽고 종료한다. 입력·코드가 바뀌면 새 state-dir과 새 버전의 검토된 계획이 필요하다.

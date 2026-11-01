# Regime190 진단·단일 개선 실험·재검증 — 2026-11-01

## 결론

기존 실데이터 **탐색 결과를 정확히 재현**했고, 근거가 있는 실패 진단과 가설 하나의 제한된 실험을 기존 Agent 2.0 큐에서 실행했다. 이틀 연속 회복 확인 가설은 학습·검증 관측 구간에서 참양성을 만들지 못해 **탐색적으로 기각**했다. **공식 개선 검증은 `BLOCKED_PIT`**, 독립 최종 holdout은 **`FINAL_HOLDOUT_CONTAMINATED`**, 모델 추론은 **`MODEL_RUNTIME_NOT_ACTIVE`**다. 실거래 준비 상태는 `NOT_READY`다.

## 시작 저장소와 호환성

운영 경로 `/home/kegor2/market-morning-reports`는 Agent 2.0 브랜치 `research/autonomous-agent-v2-architecture-20261101`의 `2c7f79e`로 유지된다. 시작 연구 worktree `/home/kegor2/market-morning-reports-regime190-e2e`는 깨끗한 `research/regime190-end-to-end-backtest-20261101`, HEAD/원격 `7009996f407dcf2266e7a4d64d3fa745fcb4a48d`였다. 새 개발 worktree `/home/kegor2/market-morning-reports-regime190-autoval`의 별도 브랜치에서만 수정했다. 시작 테스트 universal_agent 54개, regime190 28개 통과.

| 구성 | 기존 구현·검증 | 이번 재사용 | 부족한 능력·회귀 위험 |
|---|---|---|---|
| Agent 2.0 목표/가설/모델 접점 | 계약, 결정론적 테스트·재생 어댑터 | 계약 검사 | 실제 LLM 런타임 없음·낮음 |
| 오프라인 단일 큐·체크포인트 | 워커 잠금/원자적 기록, 중복·복구 테스트 | 진단 작업 1건 allowlist | 작업 분기 변경·중간 |
| Regime190 실데이터 탐색 엔진 | 6국면, 다음 시가 가정, 4,052행, 테스트 | 원본 재현·시점 검증 | PIT 미승인·낮음 |
| PIT 적격성 | 190 매트릭스와 private SQLite, 적격 0 | 독립 gate | 발표/빈티지/당시 종목군 결손·낮음 |
| 메모리/handoff | 기존 JSON, SHA·체크포인트 | 진단/실험/결정 저장 | 다중 가설 지속 계획 없음·중간 |
| 생산 체계 | 원래 저장소의 02:15 cron | 변경 없음 | 개발 worktree 분리로 위험 제한 |

## 재현, 데이터, 시점

기준 private 아티팩트·메모리 SHA와 코드 커밋을 확인하고, 동일 입력으로 전체 결과 JSON을 다시 계산했다. 이전 결과와 **정확히 일치**했다. 정규화된 결과 SHA256은 `25b812958a5750e16c7275158a4bc4623b82b47d045413eca6f3c60cf989a04f`. KOSPI/KOSDAQ 보존 CSV SHA도 각각 `b243b958...`/`a3cccdd4...`로 manifest와 일치한다. 결과 기간 2010-03-31~2026-09-15, 4,052 결정일. 경고는 당일 종가 뒤, 포지션은 다음 공통 세션 시가, 정산은 그다음 시가로 정렬했다. 한 방향 비용은 수수료 0.10%+슬리피지 0.05%다. 미래 20일 결과 라벨은 포지션 입력이 아니다.

현재 private SQLite `tasks.pit_eligible=1`은 0건이다. PostgreSQL 실제 관련 컬럼을 기존 전용 읽기 전용 계정으로 `BEGIN READ ONLY`, `statement_timeout=5000ms`, `information_schema.columns LIMIT 200`을 적용해 확인했다. 운영 데이터 행을 대량 조회하지 않았다. Naver 지수 스냅샷은 원본 발표 시각과 개정 빈티지, 거래소 캘린더, 체결 가능성이 미검증이므로 공식 성과 주장은 계속 막힌다.

## 20일 폭락 경고 진단

라벨은 결정일 종가 대비 향후 20 공통 세션 중 -10% 이하가 한 번이라도 있는 **겹치는 일별 결과**다. TP 51, FP 621, FN 159, TN 3,221; 양성 비율 **5.18%**, 정밀도 **7.59%**, 재현율 **24.29%**, 특이도 **83.84%**, 거짓 양성률 **16.16%**, 252세션 환산 거짓 경고 **38.62일**이다. 정밀도는 유병률 대비 약 1.46배다. 낮은 사건 빈도는 낮은 절대 정밀도에 기여하지만, 그것만으로 실패 원인을 증명하지 않는다.

같은 날짜·라벨에서 항상 음성, 이동평균, 변동성, 모멘텀 고정 경고를 비교했다. 변동성 경고는 탐색 정밀도 **30.57%**, 재현율 **28.10%**, 252세션 환산 거짓 경고 **8.33일**로 기존 경고보다 좋았다. 이는 동일 스냅샷의 **연관성**이며 PIT 미검증·선택 편향 때문에 독립적인 예측 우위로 결론 내릴 수 없다. 20세션 이동 블록 bootstrap의 정밀도 구간은 **1.87~12.50%**, 재현율 **6.73~37.43%**였고, 독립 사건 표본이 적어 참고 범위에 그친다. 기존 26개 라벨 군집은 검증된 실제 폭락 사건 수가 아니다. 이진 경고만 있어 PR-AUC·확률 보정은 계산하지 않았다.

## 회복 신호 진단과 실행한 단일 실험

기존 결과는 회복 신호 38일 중 TP 2, FP 36, 미래 회복 결과 89일 중 FN 87로 정밀도 **5.26%**, 재현율 **2.25%**다. 13개 신호는 이후 -5% 재하락해 거짓 반등 비율 **34.21%**였다. **15/38 신호는** 신호의 하락폭 조건(-8%)은 충족하지만 결과 라벨의 조건(-10%)을 충족하지 못했다. 이 정의 불일치는 관측 사실이다. 나머지 오탐의 인과 원인은 확인되지 않았다.

근거 기반 가설 `h_recovery_confirmation`: `RECOVERY_EARLY`를 **이틀 연속** 관측한 경우만 신호로 인정한다. 원본, 미래 결과 라벨, 거래 비용, 국면 규칙을 고정했다. 2010~2017 학습 구간 끝의 20세션을 embargo하고 2018~2021 관측 구간에 적용했다.

| 탐색 구간 | 기존 신호/TP | 변경 신호/TP | 결과 |
|---|---:|---:|---|
| 학습 1,896일 | 14 / 0 | 5 / 0 | 거짓 반등 8→4, 신호 대비 비율 57.1→80.0% |
| 검증 986일 | 6 / 0 | 2 / 0 | 참양성 0; 정밀도 개선 없음 |

참양성이 없는 두 구간의 정밀도 차이 신뢰구간은 **산출 불가**로 처리했다. 실험 결정은 `HYPOTHESIS_REJECTED_EXPLORATORY`이며 일반적인 회복 가설 전체의 반증은 아니다. 남은 제안은 전환 완충 규칙과 변동성 대비 증분 경고 검증이다. 진단 근거를 붙여 `PROPOSED_NOT_EXECUTED`로 보관했다.

## 6국면 전략과 방법론 진단

동일 4,052일·동일 시가 수익과 비용으로 비교했다. Buy-and-hold 누적 수익 **299.28%**, Sharpe **0.530**, 최대 낙폭 **-43.08%**. 6국면 노출은 **34.93%**, **0.241**, **-34.08%**였다. 6국면의 평균 노출은 **54.98%**, 일방향 총 회전은 **221**(buy-and-hold 1)이다. 정확한 로그 부의 차이 **1.08491**는 노출 기회비용 **0.75483**과 양쪽 거래 비용 차이 약 **0.33007**로 분해됐다(항등식 오차 약 `1e-15`). 방어로 피한 하락이 있었지만 놓친 상승과 잦은 비용이 더 컸다는 **회계적 설명**이다. 국면 오분류나 특정 임계값이 원인이라는 인과 결론은 아니다.

`PIT_FAILURE`, `CLASS_IMBALANCE`, `LOW_PREDICTIVE_POWER`, `LABEL_DEFINITION_PROBLEM`, `EXCESSIVE_TRANSACTION_COST`, `INSUFFICIENT_SAMPLE`을 관측 근거와 함께 기록했다. 증명되지 않은 나머지 인과 원인은 `UNKNOWN_CAUSE`로 남겼다. 근거 없는 `LOOKAHEAD_LEAKAGE`, `SIGNAL_TIMING_ERROR`, `OVERFITTING` 진단을 단정하지 않았다.

## 검증·결정·지속성

2022년 이후 구간은 **이전 아티팩트에서 이미 평가**됐다. 따라서 새 후보의 수치를 그 구간에서 계산하지 않았고 `FINAL_HOLDOUT_CONTAMINATED`로 기록했다. 2022년 이전 7개 시간순 fold와 20세션 embargo는 탐색 진단일 뿐, 과거 전체 결과가 이미 노출돼 독립 검증이라고 부르지 않는다. 통계적 유효성 `INSUFFICIENT_INDEPENDENT_EVENTS`, 표본 외 유효성 `NOT_VALIDATED`, 연구 가치 `EXPLORATORY_ONLY`, 배포 준비 `NOT_READY`다.

새 진단 작업은 기존 워커의 **단일 큐**에서 1회 실행했고 체크포인트 1과 버전 있는 진단/가설/실험/평가 JSON, 입력·코드·아티팩트 SHA, 모델 상태, 다음 행동을 비공개 연구 메모리에 기록했다. 재실행은 `ALREADY_EVALUATED`로 중복을 막고, 입력·코드·아티팩트가 바뀌면 무결성 오류로 멈춘다. 메모리 기록 직전 중단을 흉내 낸 복구 테스트에서는 워커 작업 재실행 없이 평가만 복원했다. 최대 반복 3, 이번 실행 1회, 동시 작업 1, 외부 API 요청 0, 작업 시간 상한 30초다. 활성 LLM 어댑터는 없으며 모든 진단과 가설 생성은 `DETERMINISTIC_NON_AI`다.

## 운영 안전과 다음 행동

MyDream2000 실거래·KIS 주문, MarketMorningPublisher, 운영 PostgreSQL 스키마/행, 기존 자격증명, 02:15 cron, 서비스와 기존 연구 체크포인트를 수정하지 않았다. 원래 저장소를 운영 브랜치에 둔 채 별도 worktree와 `/home/kegor2/agent2_research_state/`에만 실행 상태를 저장했다. 자격증명·대형 원천 데이터는 Git에 포함하지 않는다.

우선순위는 (1) 발표/가용 시각·빈티지·과거 종목군/거래일과 소스 권리 검증, (2) 회복 결과 라벨의 정의 정합성과 독립 사건 표본, (3) 실제로 미사용인 새 기간 또는 사전 등록된 장래 표본 확보, (4) 그 뒤 변동성 기준 대비 증분 가치와 전환 비용 검증이다. 활성 AI 런타임이 생기더라도 PIT·통계·holdout·배포 gate는 결정론적 검증으로 유지해야 한다.

## 정확한 검증·재개 명령

```bash
cd /home/kegor2/market-morning-reports-regime190-autoval
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
git diff --check

cd market-history/research
/home/kegor2/stock_env/bin/python -m regime190.autonomous_loop --state-dir /home/kegor2/agent2_research_state/regime190_autoval_v1_20261101 --repo /home/kegor2/market-morning-reports-regime190-autoval
```

동일 상태 재개는 완료 체크포인트를 읽고 종료한다. 입력이나 코드가 바뀌면 새 버전의 계획과 새 state-dir에서 다시 검토해야 한다.

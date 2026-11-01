# Regime190 Agent 4.1 연구 기록 — 2026-11-01

## 1. 구현 기능 및 Agent 4.0 대비 변경

`agent41_research.py`는 Agent 2.0/3.0/4.0 코드를 수정하지 않고 별도 연구 상태를 저장한다. 190개 지표의 기존 원본 메타데이터 네 종류를 대조해 문제·증거·미확정 원인·우선순위·필요 자원을 기록한다. 실제 20거래일 급락 실패에 대해 고정된 가설 두 개를 만들고, 허용된 2×2 범주 모델만 실행한다. 첫 후보가 검증 구간에서 기준선에 못 미치면 두 번째 후보를 실행한다. 메모리는 원자 저장과 잠금, STOP, 입력 및 산출물 해시 검사를 사용한다. 정량 결과는 탐색 전용이다.

**NOT_IMPLEMENTED:** LLM 런타임 연결, LLM의 자유 가설 생성, 연구 코드 자동 생성·수정, 변경 전후 코드 해시와 테스트 실패 시 패치 폐기. 현재 가설은 `DETERMINISTIC_RULE_TEMPLATE`이다. 연구 코드 자동 작성이나 AI 자율 연구 활성화로 표시하지 않는다. 현재 모듈은 소스 파일을 수정하거나 임의 명령을 실행하지 않는다.

## 2. 기존 기능 보존과 회귀 위험

기준은 원격 `research/regime190-agent4-market-intelligence-20261101`의 `eca181c`이다. Agent 2.0의 작업 큐·체크포인트·원자 저장·잠금·재개·중복 방지, Agent 3.0의 연구 메모리·STOP·해시·실험 기록, Agent 4.0의 여섯 국면·시장 예측·PIT 차단·신선도·검증 구간 코드는 변경하지 않았다. 새 제어기의 상태는 기존 큐와 별개이므로 새 사이클이 Agent 2.0 큐에 연결됐다고 주장하지 않는다. 회귀 위험은 기존 코드 변경이 없어 낮지만, 새 엔진의 별도 상태 체계와 기존 큐의 일관성은 **NOT_VERIFIED**다.

운영 경로 MyDream2000, MarketMorningPublisher, 운영 DB 스키마, 크론, 서비스 설정은 수정하지 않았다. 입력은 해시 검증된 로컬 Naver 지수 스냅샷과 추적된 190개 메타데이터다. 기존 운영 DB를 읽거나 쓰지 않았다. 새 상태와 산출물은 `/home/kegor2/agent2_research_state/regime190_agent41_first_20261101`에 저장했다.

## 3. PIT 재검증 및 복구 시도

190개 ID 각각에 대해 출처 후보, 관측 행, 계산 상태, 발표 시각, 과거 수정 이력을 다시 읽었다. 분류는 `PIT_BLOCKED` 71, `CALCULATION_PENDING` 21, `SOURCE_MISSING` 98, `PIT_VERIFIED` 0으로 기준과 일치했다. 항목마다 부족한 증거를 `pit_research.json`에 기록하고 전부 `BLOCKED_EVIDENCE`로 두었다. 원본 값·공식 발표 시간·빈티지의 외부 재수집과 독립 산식 검증은 **NOT_VERIFIED**다. 따라서 자동 복구 또는 PIT 승인은 0건이다. 부족한 근거만으로 원인을 확정하지 않았다.

## 4. 자율 생성 가설과 실제 실험

문제 `FORECAST-CRASH20`: Agent 4.0의 20일 급락 Brier는 여섯 국면 .0470, 단순 낙폭 .0455였다. 첫 가설 `H-CRASH-VOL-DD`는 고변동성과 큰 낙폭의 조합, 두 번째 `H-CRASH-MOM-DD`는 약한 모멘텀과 큰 낙폭의 조합이다. 1996-09-13~2017-11-29 5,334일로 평활 빈도를 학습하고, 2018-01-02~2021-12-02 966일에서 첫 가설을 실행했다. 20거래일 경계 20일을 제외했다.

| 모형 | Brier | PR-AUC(평균 정밀도) | 정밀도 | 재현율 | 양성일 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 고정 낙폭 기준선 | .045458 | .056201 | 9.65% | 28.21% | 39/966 |
| 변동성×낙폭 | .044026 | .056201 | 9.65% | 28.21% | 39/966 |

첫 후보의 Brier 차이는 -0.001432지만 정밀도·재현율·PR-AUC 개선은 없었다. 이 검증 구간은 이미 Agent 4.0에서 사용됐고, 동일 구간에서 후보를 선택했다. 두 번째 후보는 첫 후보가 Brier 기준을 통과하여 실행하지 않았다. 독립 검증은 **BLOCKED**다. 결과는 `EXPLORATORY_ONLY`이며 채택·배포하지 않았다. 급락 라벨은 겹치는 20일 창이므로 행을 독립 사건으로 해석할 수 없다. 회복 예측 실패에 대한 별도 실험은 **NOT_IMPLEMENTED**다.

## 5. 시장 예측과 검증 경계

기존 여섯 국면 및 Agent 4.0의 5·10·20일 상승·급락·회복·전환 예측 코드는 보존했다. Agent 4.1은 20일 급락 가설만 실험했으며 5·10일 및 회복의 신규 성능은 **NOT_VERIFIED**다. 국면 전환의 탐지 지연과 오경보는 독립 국면 정답이 없어 **NOT_VERIFIED**다. 2022년 이후 구간은 기존 Agent 3.0 연구에서 열람했으므로 독립 홀드아웃으로 사용하지 않았다. 데이터 마지막 날짜는 2026-10-20이며 2026-11-01의 현재 국면 또는 공식 확률을 발행하지 않는다.

## 6. 테스트·실행 결과

기존 Regime190 테스트는 원본 CSV 두 개가 새 worktree에서 Git 무시 파일이라 처음에 실패했다. Agent 4.0 worktree의 원본을 `cp -p`로 옮긴 뒤 매니페스트 SHA-256 검증을 통과했고 기존 35개 테스트가 통과했다. 기존 universal_agent 54개 테스트도 통과했다. 새 테스트는 PIT 190건 미승인, 허용 템플릿 외 입력 거부, STOP, 실행·재개·산출물 변조 차단을 확인한다. 최종 전체 Regime190 테스트 결과는 아래 명령의 실행 로그를 기준으로 한다.

실제 사이클 결과: `RESEARCH_CYCLE_RECORDED`, 문제 191건, 가설 2건, 실험 1건, PIT 승인 0건. 상태 재실행은 `ALREADY_EVALUATED`를 반환한다. 원본 수집/독립 출처 비교/LLM 호출은 수행하지 않았다.

## 7. 미해결 위험과 다음 연구 우선순위

1. 지표별 공식 발표 시각, 수정 이력, 실제 빈티지, 산식 및 대상 시장의 원본 근거를 확보한다.
2. 190건 중 계산 가능한 항목을 독립 원본 값으로 재현하고 사전 시점 검증을 자동화한다.
3. 기존 Agent 3.0/4.0에서 열람하지 않은 PIT 검증 구간을 확보한다.
4. LLM 런타임을 명시적으로 구성한 뒤 허용 파일·명령·격리 디렉터리·패치 테스트/폐기 경계를 구현한다.
5. 급락·회복 및 국면 전환을 사전 고정한 독립 검증으로 평가한다.

## 8. 권한 설정, 실행 및 재개

```bash
cd /home/kegor2/market-morning-reports-agent41
install -d -m 700 /home/kegor2/agent2_research_state/regime190_agent41_first_20261101
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m regime190.agent41_research --state-dir /home/kegor2/agent2_research_state/regime190_agent41_first_20261101
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -p 'test_*.py' -q
```

같은 실행 명령으로 재개한다. STOP 파일이 있으면 작업을 멈추고, 입력 또는 산출물 해시가 바뀌면 재실행 전에 오류로 차단한다. Git 무시 원본 CSV 두 개는 연구 worktree에 별도 복사해야 하며, 추적된 `naver_source_manifest.json`과 SHA-256이 일치해야 한다. 자동 병합이나 배포는 없다.

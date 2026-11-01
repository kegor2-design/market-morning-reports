# 범용 자율 연구 통합 진행 기록 — 2026-11-02

## 판정

**INCOMPLETE.** 세 영역의 서로 다른 템플릿 연구를 한 명령으로 연속 계산했고, 원장·재개·입력 해시 검증을 확인했다. 그러나 새 엔진은 LLM 가설 생성, Codex 자동 코드 작성, 독립 홀드아웃 검증, 실패 후 새로운 문제 발굴을 수행하지 않는다. 세 계산은 `EXPLORATORY_ONLY`이며 투자 성능이나 독립 검증 성공으로 간주하지 않는다.

## 코드 기준과 경계

- 원격 fetch 뒤 Agent 4.3 최신 브랜치 `origin/research/regime190-agent43-autonomous-development`는 `fff9b52`였다. `origin/main`은 `d424f16`이었다.
- 별도 Git worktree와 브랜치 `research/universal-autonomous-engine-20261102`를 `fff9b52`에서 생성했다. 기존 Agent 2.0~4.3 파일과 다른 저장소의 코드는 수정하지 않았다.
- 확인한 로컬 경로: `market-morning-reports-agent43`(Regime190 및 Agent 2.0~4.3), `MyDream2000`(별도 전략 저장소), `MarketMorningPublisher`(Chart Insight Engine). 새 코드에서 후자 두 저장소를 임포트하거나 변경하지 않는다.
- 새 코드: `universal_agent/autonomous.py`. `ResearchGoal`, 플러그인 프로토콜, `MARKET_REGIME`, `CHART_PATTERN`, `TRADING_STRATEGY` 구현. 기존 `locked_state`, `write_state`를 재사용한다. 상태 전이, 고유 ID, 이벤트, STOP, 스냅샷·엔진 해시, 원자 체크포인트를 제공한다. 우선순위 및 가설은 현재 고정 템플릿이다.

## 기존 기능 보존과 신규 범위

| 기능 | 기존 구현 | 이번 확인/추가 |
| --- | --- | --- |
| 작업 큐, 잠금, 원자 저장, STOP, 체크포인트, 재개, 중복 방지 | Agent 2.0 | 기존 56개 universal_agent 테스트 통과; 신규 원장도 같은 잠금·저장 사용 |
| PIT 차단, 데이터 신선도, 파일 해시 | Agent 3.0~4.1 | 기존 50개 Regime190 테스트 통과; 신규 스냅샷·엔진 해시 확인, PIT 미승인 |
| 여섯 시장 국면, 예측, Codex 실행·결과 수집 | Agent 4.0~4.3 | 기존 파일 불변 및 회귀 통과; 신규 엔진에는 연결 미완료 |
| 시장·차트·전략 공통 실행 | 없음 | 세 플러그인의 탐색 계산, 단계 원장, 재개 구현 |
| 동적 데이터 발견, LLM 계획, 자동 코드 개발, 실패 대체 연구 | Regime190의 제한된 흐름만 존재 | 범용 연결 미완료 |

## 실제 실행 증거

입력은 해시 고정한 로컬 Naver KOSPI OHLCV 스냅샷이다. 원본 7,730행 중 2007-03-02의 OHLC 0행 하나를 제외했다. 원본의 발표 시각, 빈티지, 라이선스 및 독립 원본 대조가 없어 PIT 미검증이다. 2012년 전 데이터를 훈련, 2012~2017년을 탐색 검증에 사용했다. 이 구간은 과거 연구에서 확인된 적이 있어 독립 홀드아웃이 아니다. 세 가설은 `TEMPLATE_GENERATED`다.

| 영역 | 탐색 검증 결과 | 해석 제한 |
| --- | --- | --- |
| 시장 국면 | 1,472 관측, 급락 57건; 경보 precision 0, recall 0, false alarm rate 0.0177, Brier 0.0557 | 이 경보는 실제 급락을 잡지 못했다. PR-AUC·선행 시간 미계산 |
| 차트 패턴 | 20일 돌파·거래량 조건 30건, 5일 평균 수익률 0.158%, 전체 평균 0.108% | 지수 패턴이며 개별 종목·상장폐지·유동성·역행 폭 미검증 |
| 매매 전략 | 20일 추세 필터, 비용 가정 반영 순수익률 5.70%, 최대 낙폭 -23.65%, Sharpe 0.157, 거래 전환 154회 | 지수 가상 거래; 세금·스프레드·체결·유동성 모델이 검증되지 않음 |

상태 파일: `/home/kegor2/agent2_research_state/universal_final_20261102/autonomous_state.json`. 첫 실행에서 서로 다른 연구 ID 3건, 체크포인트 24를 기록했다. 같은 명령 재실행 시 `processed_this_run=0`, 체크포인트 24였다. 공식 검증 결과는 0건, PIT 승인 0건, 차단된 독립 검증 3건이다.

기존 Agent 4.3의 LLM/Codex 호출 증거는 `/home/kegor2/agent2_research_state/regime190_agent43_final_20261101/agent43_memory.json`에 3건 있다. 이는 이번 범용 엔진의 호출이 아니다. 당시 PIT EMA 연구는 차단, 급락·회복 예측 연구는 탐색 결과 기각이었다. 새 엔진은 Codex 호출 0건이며 코드 개발 단계는 이 worktree에서 수동 구현됐다.

## 검증과 안전성

- `universal_agent` 56개, Regime190 50개 테스트 통과. 새 테스트는 세 영역 연속 실행, 재개 중복 방지, 스냅샷 해시, STOP, 불법 상태 전이를 확인한다.
- 기존 `_db_sample()`은 읽기 전용 트랜잭션, 5초 statement timeout, 테이블당 최대 20행으로 스키마를 확인했다. `SCHEMA_VERIFIED_READ_ONLY_BOUNDED`. 과거 가격 표본 20행의 `market`, 최근 금리 표본 20행의 `released_at`과 `vintage_date`는 전부 비어 있었다. DB 스키마 변경이나 쓰기 명령은 실행하지 않았다.
- 새 모듈에는 DB 접속, 주문, 서비스 제어, 네트워크, 동적 코드 실행 기능이 없다. 연구 원장만 별도 상태 경로에 쓴다. 운영 서비스 전체의 무영향을 외부 계측으로 검증하지 않았으므로 완전한 안전성 PASS로 표시하지 않는다.
- OS 수준 격리, Codex 프로세스 비밀 접근 차단, 자원별 CPU·메모리·디스크 제한은 새 엔진에 적용되지 않았다. `max_cycles=3`과 벽시계 확인만 구현했다. 새 엔진은 외부 코드 실행을 하지 않는다.

## 다음 우선순위

1. 적법한 공식 원본의 행별 발표 시각·수정 빈티지·이용 권한을 확보하고 PIT 검증한다.
2. 한 번도 모델 선택에 쓰지 않은 독립 홀드아웃과 생존 편향 없는 종목 이력을 확보한다.
3. Agent 4.3 Codex 흐름을 범용 플러그인에 연결하고, 독립 worktree·OS 격리·변경 파일 감사 및 강제 자원 제한을 검증한다.
4. 실패 분류와 중복 가설 차단을 포함한 동적 다음 과제 계획을 연결한다.

## 실행·재개

새 실행 전 권한을 먼저 설정한다. 저장소의 무시된 데이터 스냅샷은 별도 확보가 필요하다. 아래 명령은 공식 검증이 아닌 탐색 실행이다.

```bash
mkdir -m 700 /home/kegor2/agent2_research_state/new_universal_run
chmod 700 /home/kegor2/agent2_research_state/new_universal_run
cd /home/kegor2/market-morning-reports-universal
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.autonomous --goal '한국 증시 급락 위험과 차트 및 전략을 연구하라' --goal-id new-goal-1 --snapshot /home/kegor2/market-morning-reports-universal/market-history/research/daily-index-validation-20261021/naver_kospi_daily.csv --state-dir /home/kegor2/agent2_research_state/new_universal_run --max-cycles 3
```

같은 목표 ID·스냅샷·상태 경로로 재실행하면 완료 항목을 건너뛴다. STOP 파일이 있으면 실행 전 중단한다. 입력이나 엔진 코드 해시가 달라지면 새 상태 경로가 필요하다.

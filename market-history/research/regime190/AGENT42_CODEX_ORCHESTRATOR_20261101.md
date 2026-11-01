# Regime190 Agent 4.2 연구 실행 보고서 — 2026-11-01

## 1. 구현 기능과 Agent 4.1 대비 변경

Agent 4.2는 Agent 4.1의 PIT·급락 실험 산출물 및 해시를 검증하고 문제 두 건을 자동 선정한다. 우선순위는 시장 영향, 해결 가능성, 데이터 확보, 비용, 기존 연구 중복, 독립 검증 자료를 정수 점수로 계산한다. 작업마다 JSON Schema 검증을 통과한 `task.json`과 사람이 읽는 `task.md`를 만들고, 별도 작업 디렉터리에 증거를 저장한다. 공식 `codex exec`를 읽기 전용으로 호출하여 구조화 결과, 종료 코드, 제한 길이 로그, SHA-256을 수집한다. 연구 결론은 Codex 출력만으로 결정하지 않고 PIT 및 홀드아웃 게이트를 제어기가 다시 검사한다.

상태는 `READY → RUNNING → COMPLETED/BLOCKED/FAILED/REVIEW_REQUIRED`로 기록한다. `PENDING`도 계약에 예약돼 있다. 잠금과 원자 저장, STOP, 두 번의 재시도 한도, 작업별 90초 제한, 체크포인트, 입력·출력 무결성 검사, 동일 상태 재개를 구현했다. 첫 실행의 CLI 인자 오류와 샌드박스 인증 초기화 오류는 실패 기록으로 남겼고, 최종 격리 상태에서 다시 검증했다. 기존 연구 결과는 삭제하지 않았다.

## 2. 기준 및 기능 보존

원격 `research/regime190-agent41-autonomous-research`는 지정 커밋 `45fc0cba6cf9e5e1759f9195b1941e6b62be6f41`과 일치했고 이후 변경이 없었다. 새 worktree는 그 최신 상태에서 분기했다.

| 버전 | 기존 기능 | Agent 4.2 처리 | 검증 |
| --- | --- | --- | --- |
| 2.0 | 큐, 체크포인트, 잠금, 원자 저장, 재개, 중복 방지 | 기존 코드 불변. Agent 4.2는 별도 원장을 사용 | 기존 universal_agent 54개 테스트 통과 |
| 3.0 | 메모리, STOP, 해시, 실패 진단, 실험 기록 | 기존 코드 불변 | Regime190 회귀 테스트 포함 |
| 4.0 | 여섯 국면, 5·10·20일 예측, PIT 차단, 신선도, 검증 구간 | 기존 코드 불변; 기존 결과를 증거로만 사용 | Regime190 회귀 테스트 포함 |
| 4.1 | 190개 진단, 고정 가설 실험, 연구 상태·해시 | 원본 결과 해시를 재검사하고 별도 상태에 참조 | 새 테스트 포함 Regime190 47개 통과 |

기존 Agent 2.0 큐와 Agent 4.2 큐는 별개다. 동일 원장 통합은 **NOT_IMPLEMENTED**다. 기존 운영 코드·DB 스키마·cron·systemd·실거래 코드는 수정하지 않았다.

## 3. Codex 자동 실행 가능 여부

[OpenAI 공식 Codex 통합 안내](https://developers.openai.com/blog/codex-as-a-platform)는 `codex exec`를 비대화형 작업에 사용하는 인터페이스로 설명한다. 서버에는 `codex-cli 0.166.0`이 있고 ChatGPT 로그인이 확인됐다. 최종 실행에서 두 작업 모두 실제 CLI 종료 코드 0, 구조화 JSON 출력, 작업별 stdout/stderr 로그 및 출력 SHA-256을 남겼다. 이는 **실제 Codex 호출**이며 모의 실행이 아니다. 자동 호출은 작업별 90초, 최대 2작업으로 제한했다. 가격 또는 토큰의 강제 상한은 CLI에서 확인하지 못해 **NOT_VERIFIED**다.

Codex는 `--sandbox read-only`로 호출했다. 작업 지시서의 경로·명령 허용 목록은 프롬프트 및 결과 검증의 계약이며, 운영 경로 **읽기 접근까지 OS 수준에서 차단한 것은 아니다**. 셸 도구 호출 자체를 별도의 보안 샌드박스로 금지하지도 않았다. 따라서 자동 코드 수정·패치 폐기·파일 및 명령의 강제 허용 목록은 **NOT_IMPLEMENTED**다. 연구 코드 자동 편집 또는 운영 배포를 실행하지 않았다.

## 4. PIT 복구 연구 A

Agent는 관측 행이 있는 지표 1번(SMA 5·10·20·60·120·200)을 우선순위 22로 선택하고 SMA20을 조사했다. 로컬 해시 검증된 KOSPI 종가 20행으로 2020-01-02 SMA20을 부동소수점 평균과 Decimal 평균으로 각각 **2151.176**으로 재현했다. 이는 같은 원본에 대한 산술 검증이다. 독립 원본 비교나 당시 이용 가능성 증거가 아니다.

PIT 후보 범위는 현재 지표 1번의 고정 연구 템플릿으로 제한돼 있다. 190개 전체에서 새 복구 코드를 자율 생성해 후보를 고르는 기능은 **NOT_IMPLEMENTED**다.

[KRX 공식 API 설명](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES001_S2.cmd?BO_ID=EREKZauXnMmxyIlqzeDN)은 KOSPI 시리즈 일별 자료의 2010-01-04 이후 제공 범위를 보여준다. [KRX 데이터 수신 안내](https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA003.jsp)는 사용 목적에 따른 계약·권리 검토 필요성을 설명한다. KRX 원본 값을 취득하지 않았고, 행 단위 발표 시각·과거 수정 이력·독립 산식 비교도 확보하지 못했다. Codex 결과는 `EVIDENCE_BLOCKED`; 제어기 검증 결과는 `BLOCKED`; PIT 승인 **0건**이다. 190개 기존 상태는 `PIT_BLOCKED` 71, `CALCULATION_PENDING` 21, `SOURCE_MISSING` 98, `PIT_VERIFIED` 0으로 유지한다.

## 5. 시장 예측 연구 B

Agent 4.1의 실제 20거래일 급락 실험을 새 격리 상태에서 실행했고, Agent 4.2는 실패 사례를 우선순위 18로 선정했다. Codex는 준비된 수치의 차이를 재계산했다.

| 검증 구간 | 기준선 Brier | 변동성×낙폭 Brier | 차이 | 판단 |
| --- | ---: | ---: | ---: | --- |
| 2018-01-02~2021-12-02, 966일 | .045458 | .044026 | -.001432 | `EXPLORATORY_ONLY` |

2018~2021년은 Agent 4.0/4.1이 이미 사용했고, 2022년 이후도 기존 연구에서 열람했다. 독립 홀드아웃으로 재사용하지 않았다. PIT 검증도 완료되지 않았다. 정밀도·재현율·PR-AUC의 추가 개선 증거가 없으며 현재 시장 국면·공식 미래 확률을 발행하지 않는다. 국면 전환 탐지 지연·오경보, 5·10일 방향 및 회복의 Agent 4.2 신규 실험은 **NOT_VERIFIED**다.

## 6. 실제 사이클·메모리·후속 연구

최종 상태 경로는 `/home/kegor2/agent2_research_state/regime190_agent42_final_20261101`이다. 자동 선정 → 작업 지시서 → 두 Codex 실행 → 결과 수집 → 자체 게이트 검증 → 체크포인트 2 → 메모리 저장까지 실행했다. A는 `BLOCKED`, B는 `COMPLETED`(탐색 연구 처리 완료)다. 둘 다 CLI 종료 코드 0이고 각 1회 시도였다. 같은 상태로 재실행하자 체크포인트 2와 두 결론이 그대로 유지됐다.

다음 과제는 `PIT-001-OFFICIAL-RELEASE`로 자동 결정됐지만 `BLOCKED`다. 요구 자료는 공식 발표 시각, 과거 빈티지, 사용 권한이 확인된 원본 값이다. 이 자료가 없으므로 후속 과제를 Codex에 반복 호출하지 않았다. 무한 반복 방지와 검증 구간 중복 방지가 이 정지 판단의 이유다. 문제 원인은 증거 부족으로 `null/INSUFFICIENT`이며 확정하지 않았다.

## 7. 테스트와 DB 스키마

변경 전 Regime190 43개, universal_agent 54개 테스트가 통과했다. 변경 후 Regime190 **47개**, universal_agent **54개**가 통과했다. `py_compile`과 `git diff --check`도 통과했다. 신규 테스트는 작업 Schema, 우선순위, 체크포인트·재개·무결성, STOP을 검증하며 모의 Codex 결과를 사용한 단위 테스트다. 별도의 최종 사이클만 실제 Codex 실행이다.

운영 DB에는 기존 `agent3_experiments._db_sample()`의 `BEGIN READ ONLY`, 5초 statement timeout, 테이블별 최대 20행 방식으로 접속했다. 필요한 컬럼이 존재해 `SCHEMA_VERIFIED_READ_ONLY_BOUNDED`였다. 가격 20행의 과거 `market` 값은 전부 비었고, 최근 금리 20행의 `released_at` 및 `vintage_date`도 전부 비었다. `available_at` 컬럼 존재는 PIT를 증명하지 않는다. 어떤 DB 쓰기나 스키마 변경도 하지 않았다.

## 8. 위험, 다음 우선순위 및 실행·재개

PIT 공식 원본 값과 시점별 빈티지, 독립 예측 홀드아웃이 가장 큰 차단 조건이다. Codex 읽기 접근 범위를 OS 수준에서 강제하지 못하므로 현재는 비민감한 단계별 증거만 전달한다. LLM의 연구 제안은 검증 구간을 반복 최적화할 수 있어, 새 증거를 확보하기 전에는 후속 실험을 차단한다. 자동 코드 수정은 별도 격리 런타임, 파일·명령 강제 허용 목록, 사전·사후 해시와 실패 시 폐기를 구현한 뒤 다뤄야 한다.

```bash
cd /home/kegor2/market-morning-reports-agent42
install -d -m 700 /home/kegor2/agent2_research_state/regime190_agent42_source_20261101
install -d -m 700 /home/kegor2/agent2_research_state/regime190_agent42_final_20261101
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m regime190.agent42_orchestrator --state-dir /home/kegor2/agent2_research_state/regime190_agent42_final_20261101 --agent41-state /home/kegor2/agent2_research_state/regime190_agent42_source_20261101 --max-tasks 2 --timeout 90
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -p 'test_*.py' -q
```

새 worktree에는 Git 무시 파일인 Naver 원본 CSV 두 개가 필요하며 추적된 매니페스트 SHA-256과 일치해야 한다. 서버 샌드박스에서는 Codex 인증 세션 초기화에 추가 실행 권한이 필요했으며 허가 후 실제 CLI가 작동했다. STOP 파일을 두면 다음 작업은 실행하지 않는다. 재개 명령은 위와 동일하다. 자동 병합·실거래 배포는 없다.

## 최종 질문에 대한 답

**부분적으로 가능하다.** Agent는 사람의 새 연구 지시 없이 두 과제를 선정하고 Codex를 실제 호출해 결과를 평가·저장했으며, 다음 과제를 선정했다. 다만 다음 과제는 공식 PIT 원본·시점 증거가 없어 `BLOCKED`다. Codex를 통한 연구 코드 자동 수정과 독립 성능 검증은 구현 또는 근거가 부족하므로 완전 자율 연구 시스템으로 판단하지 않는다.

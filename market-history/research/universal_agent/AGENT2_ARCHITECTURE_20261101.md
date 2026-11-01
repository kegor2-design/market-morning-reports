# MyDream2000 Research Agent 2.0 — 2026-11-01

## 시작 상태와 검증 기준

- 저장소: `market-morning-reports`; 시작 브랜치 `research/regime190-credential-pit-20261101`, 시작 HEAD `9fefdd4` (보고서 커밋). 최신 연구 코드 커밋은 `4e3fc3a`이며 앞선 `25264c8`, `0c08f20`, `534be00`, `31f070d`를 포함한다. `git ls-remote --heads origin`으로 세 연구 브랜치의 원격 HEAD를 확인했다.
- 시작 작업 트리는 깨끗했다. MyDream2000 `production`과 MarketMorningPublisher `main`에는 별개의 미커밋 작업이 있어 읽기만 했다. 연구 저장소 밖의 코드, DB, cron, 서비스는 변경하지 않았다.
- 시작 테스트: universal_agent 48/48 통과. 변경 후 universal_agent 54/54, regime190 23/23 통과. `git diff --check` 통과.
- 실제 private 오프라인 상태의 `research_status.json`은 체크포인트 3, `BACKTEST_BLOCKED`였다. 이는 이번 합성 실험의 상태와 별개다.
- 호스트: 2 vCPU, RAM 3.8 GiB(점검 당시 가용 2.9 GiB), 디스크 여유 47 GiB. 02:15 KST `REGIME190_OFFLINE_RESEARCH` cron이 있으며 `regime190/worker.py --service-loop` 프로세스가 실행 중이었다. 둘 다 그대로 두었다.

## 기능 보존 행렬

| 기능 | 출처 브랜치 | 출처 커밋 | 현 상태 | 재사용 계획 | 회귀 위험 |
|---|---|---|---|---|---|
| Phase 4/5 supervisor | data-audit 선행 이력 | `31f070d` | 구현·기준 테스트 통과 | 변경 없음 | 낮음 |
| 영속 작업 큐 | data-audit | `534be00` | 구현·기준 테스트 통과 | `task_queue.json` 단일 실행 원장 | 중간: 새 task 형식 |
| 오프라인 워커 | data-audit, credential-pit | `534be00`, `4e3fc3a` | 구현·기준 테스트 통과 | 등록된 합성 어댑터만 추가 | 중간: allowlist 변경 |
| 체크포인트 복구 | data-audit | `534be00` | 구현·기준 테스트 통과 | 기존 hash/lock/atomic write 재사용 | 중간 |
| 중복 방지 | data-audit | `534be00` | 구현·기준 테스트 통과 | 완료 큐 및 연구 메모리로 재실행 차단 | 낮음 |
| 자원 한도 | data-audit | `0c08f20` | 구현·기준 테스트 통과 | 워커 hard limit과 1-task fixture 한도 | 낮음 |
| PIT blocker 분류 | evidence-discovery | `6b806e9` | 구현·테스트 통과 | 변경 없음, 실데이터 연구에서 계속 사용 | 낮음 |
| 소스 발견 | evidence-discovery | `97d8e66` | 구현·테스트 통과 | 변경 없음 | 낮음 |
| 제공자 역량 확인 | credential-pit | `4e3fc3a` | 구현·테스트 통과 | 변경 없음 | 낮음 |
| 자격증명 보안 | credential-pit | `4e3fc3a` | 구현·테스트 통과 | 합성 경로는 자격증명 접근 없음 | 낮음 |
| 증거 출처 | credential-pit | `4e3fc3a` | 구현·테스트 통과 | artifact SHA, tool/data/model 버전 기록 | 중간: 연구 해석 별도 검증 필요 |
| 연구 handoff | data-audit | `534be00` | 구현·기준 테스트 통과 | 기존 handoff 보존, Agent 2.0 전용 요약 추가 | 낮음 |
| cron 호환성 | data-audit | `534be00` | 02:15 항목 확인 | 기존 실행 경로 불변 | 낮음 |
| 운영 격리 | 전 브랜치 | `534be00`, `4e3fc3a` | 기존 경계 구현; 새 합성 경로 테스트 | 실거래·게시·DB 연결 없음 | 중간: 향후 도구 활성화 시 |

## 실제 자율성 평가

`IMPLEMENTED_AND_VERIFIED`: 규칙 기반 작업 순서, 의존성, allowlist 실행, 큐/체크포인트, 중복 방지, bounded retry, 기존 PIT 차단, 운영 격리. `IMPLEMENTED_NOT_VERIFIED`: 장기간 무인 운영 전체의 복구 능력. `PARTIALLY_IMPLEMENTED`: 목표/가설/계획/평가 계약, 도구 발견, 영속 연구 메모리, 예산, handoff. `NOT_IMPLEMENTED`: 모델 기반 목표 해석·가설 생성·실험 설계·자율 재계획·새 도구 코드 생성/검토/활성화. `BLOCKED_BY_EXTERNAL_DEPENDENCY`: 실제 모델 런타임과 그 승인, 실데이터 PIT 증거 및 필요한 라이선스.

기존 Phase 4/5, runner, supervisor, offline worker는 **RULE_BASED_AUTOMATION**이다. Codex handoff는 **AI_ASSISTED_RESEARCH**의 수동 접점이다. **MODEL_DRIVEN_AUTONOMOUS_RESEARCH**는 현재 `NOT_ACTIVE`다. 결정론적 테스트 플래너의 결과를 AI 추론으로 부르지 않는다.

## 목표 구조와 경계

`Research Director → ModelAdapter(Planner) → schema/permission gate → tool registry → existing offline_worker/task_queue.json → artifact verification → ModelAdapter(Evaluator) → research_memory.json → next proposal/handoff`.

Director의 장기 우선순위·중단 판단은 설계 단계다. 이번 구현은 `ModelAdapter` 프로토콜, 결정론적 테스트 어댑터, 저장된 결정의 오프라인 replay, 합성 분석 도구, 별도 연구 메모리와 handoff만 제공한다. `task_queue.json`만 실행 상태를 소유한다. 메모리는 과학적 판단과 참조를 저장하며 실행 상태를 복제하지 않는다. 합성 도구는 고정된 `agent2_synthetic` 워커 어댑터에서만 실행되고 네트워크·DB·trading credential을 사용하지 않는다.

도구 레지스트리 계약은 `tool_id/version/input_schema/output_schema/permissions/resource_limits/side_effects/test_status/execution_environment`이다. 현재 등록 도구는 `synthetic_signal_check` 하나다. 새 도구 제안은 `CODEX_REQUIRED` 명세로만 허용하며 격리 구현→정적 검사→단위 테스트→보안 검토→회귀 검사→승인→활성화 단계를 거쳐야 한다. 이번 단계에는 코드 생성과 자동 활성화가 없다.

## 계약과 마이그레이션

- 목표 v1: `objective_id/domain/question`. 가설 v1: `hypothesis_id/objective_id/statement/falsification`.
- 계획 v1: 목표, 가설, 요구 데이터, PIT 조건, 실험 방법, 평가 지표, 실행 예산, 의존성, 성공·실패 기준, 다음 행동, 도구 ID, 실행 등급.
- Agent 2.0 작업 v2: `agent2_task_contract_version=2`와 목표/가설 ID, 도구, 데이터, PIT, 실행 등급, 예산, 검증 규칙, 예상 아티팩트, 재시도 정책. 기존 워커의 queue v1 필드는 그대로 유지한다. 변환은 새 `agent2_synthetic` plan에만 적용된다. 기존 Regime190 queue v1을 자동 변환하거나 재해석하지 않는다.
- 결과: 워커의 JSON 아티팩트, task/checkpoint ID, SHA256, tool/data/model 버전. 평가: `execution_success`, `data_validity`, `statistical_validity`, `research_value`, 가설 결과와 다음 제안. 성공적인 실행은 연구 성공을 뜻하지 않는다.
- 별개 증거 상태: `DATA_AVAILABLE → CALCULATION_VALID → PIT_VALID → BACKTEST_ELIGIBLE → BACKTEST_VERIFIED`. 합성 결과는 이 사슬을 전혀 진전시키지 않는다.
- 승인 필요: 운영 매매/배포, 유료 API와 반복 모델 비용, 상주 서비스, DB 스키마, 파괴 작업, 미승인 라이선스, 운영 자격증명. 승인 부재는 거절/대기 상태이며 자동 실행 근거가 아니다.

## 실행 경계와 다음 단계

이번 루프는 1 task/10초의 고정 예산, STOP 파일, 완료 메모리 검사로 종료한다. CLI를 cron에 연결하지 않았다. 동일 목표의 새 실험, 실제 증거의 모델 평가, 다중 반복과 자동 재계획은 아직 없다. 외부 데이터의 publication/available/vintage timestamp, 당시 종목 구성, 기업행위, 거래 비용, 표본 수 및 out-of-sample 검증 없이는 성과 주장을 하지 않는다.

실제 독립 CLI 실행(`/tmp/mydream-agent2-20261101-final`): 작업 `synthetic_mean_positive` 완료, 워커 checkpoint 1, 다음 작업 없음. 결과 `sample_size=3`, `mean=2.0`, `SYNTHETIC_VALID`, `NOT_ASSESSED`, `FIXTURE_ONLY`, `MOCKED_PLANNER_NOT_AI`; 1회 예산으로 종료. 동일 목표 재실행은 `ALREADY_EVALUATED`이며 체크포인트는 1을 유지했다. 합성 수치로 역사적 성과를 주장할 수 없다.

이번 실행에는 운영 DB 접근이 필요하지 않았다. 실제 DB 테이블/컬럼 스키마 조회를 수행하지 않았으며 DB 스키마 검증 상태는 `NOT_PERFORMED_NOT_REQUIRED`다. 운영 DB 스키마, API 자격증명, 02:15 cron, 서비스와 trading 코드는 변경하지 않았다.

모델 런타임 선택: 원격 API는 서버 자원 부담이 적지만 비용·민감 데이터 필터·네트워크와 승인 관리가 필요하다. 로컬 모델은 반복 API 비용이 없을 수 있으나 2 vCPU/3.8 GiB RAM에서 충분한 추론 품질과 지연을 검증하지 못했다. Codex handoff는 현재 가장 안전한 수동 경로이며 자동 재개 기능이 아니다. 실제 어댑터는 구조화 출력, schema 검사, timeout, 제한된 재시도·토큰·요청 예산, 감사 로그, 민감 정보 필터와 결정론적 실패 처리를 먼저 갖춰야 한다. 유료 추론과 상주 서비스는 활성화하지 않았다.

우선순위: (1) 모델 제공자와 예산/보안 승인, (2) 읽기 전용 실데이터 도구의 PIT·라이선스 검증, (3) 결과 평가의 표본·편향·out-of-sample 기준, (4) 다중 연구 주기와 일일 요약의 격리 테스트, (5) 도구 후보 검토 워크플로, (6) 승인 후 운영 스케줄 검토.

검증 명령:

```bash
cd /home/kegor2/market-morning-reports
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
git diff --check
```

격리된 합성 실행 및 재개 명령(같은 state-dir로 재실행하면 완료 상태를 읽고 종료):

```bash
cd /home/kegor2/market-morning-reports/market-history/research
/home/kegor2/stock_env/bin/python -m universal_agent.agent2 --state-dir /tmp/mydream-agent2-20261101 --repo /home/kegor2/market-morning-reports --objective universal_agent/fixtures/agent2_objective.json
```

실제 Regime190 워커는 기존 02:15 cron에서만 실행한다. Agent 2.0 합성 CLI를 그 cron 또는 운영 DB에 연결하지 않는다.

# Regime190 Agent 4.3 연구 실행 보고서 — 2026-11-01

## 기준과 기능 보존

원격 기준 브랜치 `research/regime190-agent42-codex-orchestrator`는 작업 전 `c85c5ddd499d775cc5fd7608f7d3eeff1fec7165`였다. Agent 4.3 worktree는 이 커밋에서 분기했다. Agent 2.0~4.2 파일은 수정하지 않았다.

| 버전 | 보존된 기능 | 확인 |
| --- | --- | --- |
| 2.0 | 큐, 잠금, 원자 저장, 체크포인트, 재개, 중복 방지 | universal_agent 54개 테스트 통과 |
| 3.0 | STOP, 해시, 실패 진단, 연구 메모리 | 기존 파일 불변, Regime190 회귀 50개 통과 |
| 4.0 | 여섯 국면, 방향·급락·회복 탐색, PIT 게이트 | 기존 파일 불변, Regime190 회귀 통과 |
| 4.1 | PIT 190개 진단, 고정 가설 실험 | 기존 파일 불변, Regime190 회귀 통과 |
| 4.2 | Codex 작업 지시, 결과 수집, 체크포인트·재개 | 기존 파일 불변, Regime190 회귀 통과 |
| 4.3 | LLM 가설과 Python 실험 코드, 격리 실행, 두 fold 평가 | 신규 `agent43_engine.py`, schema, 테스트 |

Agent 4.3의 상태 원장은 기존 Agent 2.0 및 4.2 원장과 분리돼 있다. 완전 통합은 구현하지 않았다.

## 실제 연속 실행

원래 실행 상태는 `/home/kegor2/agent2_research_state/regime190_agent43_final_20261101`이다. 세 번의 실제 Codex CLI 호출에서 구조화 가설과 Python 코드가 생성됐다. 첫 실행에서 PIT 과제는 성공적으로 계산됐으나 공식 PIT 증거 부재로 차단됐다. 예측 두 건은 생성된 코드가 당시 코드 검사기에 걸려 실패했다. 검사기를 수정한 다음, 동일 입력 해시와 이전 Codex 출력 로그를 확인하고 코드 버전 변경 감사 기록을 남겨 **기존 산출물을 재실행**했다. 추가 LLM 호출은 없었다. 체크포인트는 1에서 3으로 진행했고, 각 예측 결과를 다시 채점해 기각 사유를 메모리에 기록했다. 이 재실행을 새로운 LLM 생성 호출로 세지 않는다.

2026-11-12에 원래 상태를 연구 worktree의 `.agent43_private/final_migrated_20261112`로 복사했다. 새 경로의 입력·코드·결과 해시를 확인하고 엔진 버전 변경을 `code_revision_3.json`에 기록했다. 동일 상태 재개는 체크포인트 3, Codex 호출 3회를 유지했다. 이 이동은 새 LLM 호출이나 새 격리 실행이 아니며 원래 실행 위치의 이력을 바꾸지 않는다. 이후 새 상태는 연구 worktree 내부의 `.agent43_private`에서만 생성되도록 코드가 검사한다. 별도 확인 시도 `.agent43_private/final_20261106`은 Codex 인증 세션 초기화가 서버 샌드박스에 막혀 세 작업 모두 CLI 종료 코드 1로 끝났다. 이 실패도 삭제하지 않았다.

| 순서 | 가설 ID | 실제 코드 작업 및 결과 | 판정 |
| --- | --- | --- | --- |
| 1 PIT-EMA20 | `H-EMA20-SEED-60` | 60개 종가의 EMA20 초기값 두 방식을 Codex 생성 코드로 계산. 최종값 2165.837589와 2165.788877, 차이 0.048712. 별도 Decimal 계산으로 같은 원본의 산술 검산 | `BLOCKED_EVIDENCE`: 공식 발표 시각, 빈티지, 독립 원본 없음 |
| 2 FORECAST-CRASH20 | `H-KOSDAQ-DIVERGENCE-01` | KOSDAQ 상대성과 KOSPI 추세의 괴리 가설 코드 생성. 숨긴 검증 레이블을 호스트에서 채점 | 두 fold의 Brier 차이 +0.003029, +0.002178. 가설 기각, `EXPLORATORY_ONLY` |
| 3 FORECAST-RECOVERY10 | `H-KOSDAQ-LEADERSHIP-REBOUND-01` | KOSDAQ 선행 회복 가설 코드 생성. 숨긴 검증 레이블을 호스트에서 채점 | 두 fold의 Brier 차이 +0.000534, +0.000132. 가설 기각, `EXPLORATORY_ONLY` |

예측 fold는 2012~2014와 2015~2017이며 훈련과 검증을 시간 순서로 나누고 20거래일을 제외했다. 첫 fold 검증 720행, 둘째 717행이다. 과거에 검토한 구간이므로 독립 홀드아웃이 아니다. 급락 양성은 각각 12일, 4일이고 회복 양성은 1일, 0일이다. 특히 회복 지표의 해석력은 매우 낮다. Precision, Recall, PR-AUC, Brier, 5-bin ECE, 오경보율을 산출했으나 전환 지연은 독립 정답이 없어 검증하지 못했다. 공식 예측 모델에는 어느 지표도 투입하지 않았다.

## PIT 및 데이터

190개 전체 순위를 다시 계산했다. 분류는 `PIT_VERIFIED=0`, `PIT_BLOCKED=71`, `CALCULATION_PENDING=21`, `SOURCE_MISSING=98`이다. 2번 EMA20을 수식 재현 후보로 선정해 실제 계산했다. 원본은 로컬 해시 고정 KOSPI 종가 스냅샷이며 공식 발표 시간, 수정 이력, 독립 값 비교가 없다. PIT 승인 0건을 유지한다. 정식 연구 채택에 필요한 KRX 등 공식 출처와 라이선스·빈티지 증거를 확보하지 못했다.

운영 DB는 기존 `_db_sample()`로 `BEGIN READ ONLY`, 5초 제한, 테이블당 최대 20행만 조회했다. 세 테이블의 필수 컬럼은 존재했다. 과거 가격 표본 20행의 `market`은 모두 비었고, 최근 금리 표본 20행의 `released_at`, `vintage_date`도 모두 비었다. 스키마 호환성은 표본 범위에서 확인됐지만 이 데이터로 PIT를 승인할 수 없다.

## 안전성, 제약, 부작용

생성된 Python 실험은 원래 실행에서 `bwrap --unshare-all`과 `/work` 단일 쓰기 바인드로 실행했고, 운영 홈·DB 비밀·네트워크를 전달하지 않았다. CPU 15초, 메모리 256 MiB, 파일 크기 10 MiB 제한을 적용했다. 현재 보존된 생성 코드는 연구 worktree 내부 Git 무시 디렉터리에 있으며 새 상태도 그 경로로 제한한다. **새 경로에서 격리 실행을 다시 수행하지는 못했다.** Codex 자체는 읽기 전용 샌드박스로 호출했으나 Codex 프로세스의 읽기 가능 경로를 OS 수준에서 연구 디렉터리로 제한하지 못했다. 원래 실행의 worktree 외부 코드 저장 이력도 남는다. 운영 코드·DB·cron·systemd·주문 코드를 편집하거나 운영 브랜치에 병합하지 않았다. DB 무쓰기와 서비스 무영향은 실행 경로 및 읽기 전용 트랜잭션으로 뒷받침되지만 운영 전체에 대한 완전한 외부 감시는 수행하지 않았다.

Codex 호출은 최대 3회, 과제별 90초, 실험 15초, 최대 3사이클, 재시도 2회, STOP·잠금·원자 저장·입출력 해시를 적용했다. 토큰 또는 금액 상한은 CLI에서 강제하지 못했다. 실제 `codex_calls=3`만 강제된 한도다. 실패한 두 가설의 Brier 악화를 기록하고 동일 가설 무한 반복을 막았다. 다음 과제 `ACQUIRE_PIT_AND_UNEXAMINED_HOLDOUT`는 외부 증거가 없어 `BLOCKED`이며 자동 호출을 중단한다.

Agent 4.3은 현재 세 개의 미리 정의된 문제 중 우선순위를 선택한다. LLM이 가설은 새로 만들지만, 완전히 새로운 문제를 발굴하고 임의의 다음 연구를 설계하는 개방형 루프는 구현하지 않았다. 독립 검증, 공식 PIT 복구, 연구 worktree 안의 코드 작성, Codex 프로세스의 OS 수준 격리는 미완료다.

## 검증 및 실행·재개

기존 실행에서 Regime190 50개, universal_agent 54개 테스트가 통과했다. worktree 상태 경계 변경 후 Regime190 **51개**, universal_agent **54개**, `py_compile`, `git diff --check`가 통과했다. 읽기 전용 DB 표본도 `SCHEMA_VERIFIED_READ_ONLY_BOUNDED`였으며 가격 표본의 과거 시장 구분과 최근 금리 표본의 발표·빈티지 값은 여전히 비어 있었다. 현재 코드와 데이터 버전, 입력·출력 해시는 상태 원장에 있다. 동일 상태로 재실행하면 체크포인트 3을 유지한다.

```bash
cd /home/kegor2/market-morning-reports-agent43
install -d -m 700 /home/kegor2/market-morning-reports-agent43/.agent43_private
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m regime190.agent43_engine --state-dir /home/kegor2/market-morning-reports-agent43/.agent43_private/final_migrated_20261112 --max-cycles 3
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -p 'test_*.py' -q
```

새 상태에서 처음부터 실행하려면 `.agent43_private` 아래에 권한 700의 별도 디렉터리를 만들고 같은 명령의 `--state-dir`을 바꾼다. 새 실행은 추가 Codex 호출을 발생시키며 Codex 인증 세션 초기화와 bubblewrap 실행 권한이 필요하다. STOP 파일을 상태 디렉터리에 만들면 다음 작업 전에 멈춘다. 외부 원본과 독립 홀드아웃을 확보한 다음 PIT 증거 검증을 최우선으로 진행한다.

## 최종 판단

**부분적으로 가능하다.** 사람의 추가 연구 지시 없이 세 과제를 선택하고 실제 LLM 가설·연구 코드를 생성해 격리 실행, 탐색 백테스트, 메모리·재개 및 다음 과제 차단까지 수행했다. 독립 검증과 공식 PIT 승인은 불가능했고 두 예측 가설은 기각됐다. 완전한 자율 연구·개발 엔진이라는 결론은 내릴 수 없다.

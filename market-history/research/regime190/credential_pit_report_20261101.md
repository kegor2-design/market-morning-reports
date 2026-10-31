# Regime190 자격증명·PIT 증거 인계 — 2026-11-01 KST

## 1. 기준선과 격리

- 시작 작업 트리: `research/regime190-evidence-discovery-20261101`, HEAD `25264c82106eaac40f4e2332c36e3df0533ada24`, 원격 HEAD 일치, 변경 파일 없음. 이전 연구 브랜치 `research/regime190-data-audit-20261027`의 원격 HEAD는 `0c08f206a7a5b4c2f2a659d9bb224040397e9516`.
- 개발 브랜치: `research/regime190-credential-pit-20261101`. 기존 Phase 4/5 supervisor, Runner, 오프라인 워커, 운영 계획 및 02:15 KST cron 설정을 보존했다.
- 운영 큐는 시작 시 체크포인트 3, 해시 일치. 기존 연구 워커 서비스 루프와 수집 오케스트레이터가 실행 중이었다. 초기 서버 자원은 2 vCPU, 사용 가능 메모리 약 2.8 GiB, 여유 디스크 47 GiB였다.
- 변경 전 공통 테스트 47개, Regime190 테스트 16개 통과.

## 2. 기존 자격증명과 실제 접근 결과

환경 파일을 실행하지 않고 `KEY=VALUE` 형식으로 읽었다. 키 이름별 값의 존재 여부만 산출물에 남겼고 값은 출력·복사·커밋하지 않았다. `mydream2000.env`에는 KIS, ECOS, FRED, DART 항목이 있고 `MarketMorningPublisher/.env`에는 KRX 로그인 항목이 있다. KOSIS API 키는 두 파일에서 확인되지 않았다. 별도 `mydream2000_backtest_ro.env`의 DB 계정은 읽기 전용 연결을 검증했다.

| 제공자 | 자격증명 | 실제 인증·접근 | 확인 범위 | 권리 상태 / 다음 조치 |
| --- | --- | --- | --- | --- |
| KIS | 있음 | `NOT_TESTED_TOKEN_STATE_PROTECTED` | 운영 토큰을 새로 발급하거나 교체하지 않음 | 시세 사용·재배포 범위 확인 후 격리 인증 설계 |
| KRX | 로그인 있음 | `NOT_TESTED_LOGIN_STATE_PROTECTED` | 로그인 세션 변경 없음 | 데이터 상품 권리 및 과거 상장·상폐 범위 확인 |
| BOK ECOS | 있음 | `SUCCESS`, HTTP 200 | `817Y002` 국고채 10년 2020-10-05의 최대 1행, 응답 필드·해시만 기록 | `LICENSE_REVIEW_REQUIRED`; 발표 시각·빈티지 미확인 |
| KOSIS | 없음 | `NO_CREDENTIAL` | 공개 문서만 확인 | 승인된 키와 표별 이용조건 필요 |
| FRED | 있음 | `SUCCESS`, HTTP 200 | DGS10·DGS2 메타데이터와 최초 발표 형식 표본 | 두 시리즈의 공개영역·출처 표시 조건 확인; 더 넓은 활용은 검토 |
| OpenDART | 있음 | `SUCCESS`, API `000` | 2020-10-05 접수 검색 최대 1행, 응답 필드·해시만 기록 | `LICENSE_REVIEW_REQUIRED`; 접수일은 접수 시각의 증거가 아님 |

ECOS·DART 인증 확인 응답 원문과 값은 저장하지 않았다. 해당 조회 성공은 해당 날짜와 필드 한 건의 접근만 뜻하며 목표 기간 전체, 상폐 종목, 개정 이력 또는 PIT 사용 가능성을 뜻하지 않는다. 실제 호출 한도는 ECOS·DART 각 1회, FRED 각 시리즈 최대 3회로 제한했다. 제공자의 전체 요금·호출 정책은 검증하지 못했다.

FRED 시리즈 메타데이터의 관측 범위는 DGS10 `1962-01-02~2026-10-29`, DGS2 `1976-06-01~2026-10-29`이며 둘 다 일별이다. 이는 API 메타데이터의 범위로, 전 기간의 빈티지·발표 시각 완전성을 검증한 결과가 아니다. ECOS와 DART는 각각 단일 날짜에서만 행이 확인됐다. KIS·KRX·KOSIS의 인증된 과거 자료 범위는 확인되지 않았다.

이번 접근 확인으로 과거 상장 종목군, 상장폐지 종목, 기업행위 조정 정책을 입증한 제공자는 없다. FRED 금리 두 시리즈는 주식 종목군 증거가 필요하지 않지만 실제 발표 시각이 없어 의사결정 시점의 사용 가능성을 입증하지 못한다.

공식 근거: [FRED DGS10](https://fred.stlouisfed.org/series/DGS10), [FRED DGS2](https://fred.stlouisfed.org/series/DGS2), [FRED 관측값 API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html), [FRED 이용 조건](https://fred.stlouisfed.org/docs/api/terms_of_use.html), [OpenDART 공시 검색](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001), [KIS 사용 범위](https://apiportal.koreainvestment.com/about-open-api), [KRX 서비스 목록](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd), [KOSIS 공유서비스](https://kosis.kr/serviceInfo/openAPIGuide.do).

## 3. 실제 증거 획득과 PIT 재평가

지표 116(미국 2년·10년 국채금리)을 선택했다. 기존 자료는 월별 일부 구성요소 및 현재 개정값 위주이고 두 금리의 최초 발표 빈티지·발표 시각 검증이 없었다. 기존 FRED 매핑 `DGS10`, `DGS2`와 공식 페이지의 `Public Domain: Citation Requested` 분류를 확인한 뒤 2020년 1월 표본만 요청했다.

| 구성요소 | 최초 발표 형식 (`output_type=4`) | 수치 / 결측 | 빈티지 시작일 범위 | 비공개 원문 SHA-256 |
| --- | --- | --- | --- | --- |
| DGS10 | 23행 | 21 / 2 | 2020-01-03 ~ 2020-02-03 | `14e4e5cd36654c4c0d83f9c6549def058d370a23c7c3bdc081f6dbef7b17e088` |
| DGS2 | 23행 | 21 / 2 | 2020-01-03 ~ 2020-02-03 | `bb964712713ad3df1b1767f00fe07aeaed09e512f445f80224b5d5868d0c8b52` |

원문은 `~/MyDream2000/research/universal_agent/regime190-credential-pit-20261101-v2/raw`에 보관된다. 디렉터리 권한 0700, 파일 0600, 응답 체크섬 일치, 빈티지 관측 키 중복 0, 키 문자열 미포함을 확인했다. 원문과 자격증명은 Git에 넣지 않았다. 제공자·시리즈·비밀 없는 URL·조회 시각·관측일·빈티지 날짜·라이선스 분류·체크섬·실행 ID를 태스크 산출물에 남겼다. **과거 발표 시각은 원문에 없어 `null`로 기록했다.** 빈티지 시작 날짜를 발표 시각으로 간주하지 않았다.

두 구성요소의 2020년 1월 표본 획득으로 지표 116의 ‘DGS2 구성요소 없음’은 그 표본 범위에서 해소됐다. 전체 2010~2026 기간, H.15 실제 발표 시각, 의사결정 시점 가용성, 독립 계산·정의 검증은 미완료다. 최종 재평가는 `PIT_BLOCKED`; 새 `PIT_VERIFIED`는 **0개**이고 역사 백테스트는 실행하지 않았다.

## 4. 190개 매핑과 자율 작업

현재 감사 파일·비공개 SQLite에서 190개를 다시 계산했다. 기존 PIT 분류는 `PIT_BLOCKED` 71, `CALCULATION_PENDING` 21, `SOURCE_MISSING` 98, `PIT_VERIFIED` 0으로 유지된다. 주 차단 원인은 `MISSING_SOURCE` 98, `MISSING_TIMESTAMP` 92다. 중복 허용 세부 결손은 발표 시각 190, 개정 이력 190, 계산 검증 190, 원천 98, 주식 종목군 66, 기업행위 정책 32다. 주식 종목군·기업행위는 해당 주식 기반 계열에만 적용하도록 현재 분류를 보정했다.

`map_provider_capabilities_190` 산출물은 각 지표의 필요 필드, 보유 필드, 결손, 후보 제공자, 실제 접근 상태, 권리 상태, PIT 요건, 다음 작업과 증거 지문을 담는다. 후보 매핑 수는 KRX 106, KIS 106, ECOS 23, FRED 12, DART 20이며 **실제 제공 가능 지표 수가 아니다**. 다음 작업 분류는 서버 실행 가능 13, Codex 검토 42, 권리 확인 필요 135이다. 이 수치는 계획 후보이며 신규 예약 작업 수가 아니다.

버전 1 연구 태스크 계약은 목표, 가설, 필요 증거, 의존성, 실행 권한, 자원 한도, PIT 선행조건, 검증법, 성공 기준, 실패 분류, 다음 작업을 기록한다. 기존 정식 큐와 체크포인트를 재사용하며 유료 모델·상시 추론 서비스는 추가하지 않았다. 실제 큐에서 DGS10 증거 해시를 감지해 DGS2 수집과 재평가를 한 번씩 자동 생성했다. 마지막으로 190개 제공자 매핑을 생성했다. 체크포인트 7, 큐 해시 일치, 재실행 처리 0건이다.

## 5. 안전·검증 및 남은 작업

운영 PostgreSQL 계정의 `transaction_read_only=on`을 확인하고, `domestic_daily_price`, `historical_backfill_run`, `economic_indicator_vintage`, `market_rates_snapshot`, `domestic_investor_daily`, `market_fx_snapshot`의 실제 컬럼을 조회했다. `statement_timeout=5s`로 제한했고 해당 점검 시 활성 세션 수는 1이었다. 새 수집은 운영 DB에 쓰지 않았고 운영 서비스·거래 로직·토큰·환경 파일·cron·운영 체크포인트를 변경하지 않았다.

최종 회귀 테스트는 공통 48개, Regime190 23개가 통과했고 Python 컴파일과 Git diff 검사가 통과했다. 원격 커밋 SHA는 최종 인계 메시지에서 확인한다. 현재 `CODEX_REQUIRED`는 `dgs2_release_design`이며 실제 후속 초점은 H.15 발표 시각, 전체 기간과 시차·휴일, 계산 정의 확인이다. `HUMAN_APPROVAL_REQUIRED`는 `provider_rights_review`로, 더 넓은 제공자 데이터 보관·상품 이용·재배포 범위를 결정해야 한다. 지금 큐에 남은 `SERVER_EXECUTABLE` 작업은 0개다. 권리·출처별 PIT 증거가 새로 확인되면 증거 지문을 바탕으로 새 제한 계획을 검토한다.

## 6. 정확한 확인·재개 명령

```bash
install -d -m 700 /home/kegor2/MyDream2000/research/universal_agent/regime190-credential-pit-20261101-v2
cd /home/kegor2/market-morning-reports/market-history/research
/home/kegor2/stock_env/bin/python -m universal_agent.offline_worker status --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-credential-pit-20261101-v2 --repo /home/kegor2/market-morning-reports
/home/kegor2/stock_env/bin/python -m universal_agent.offline_worker run --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-credential-pit-20261101-v2 --repo /home/kegor2/market-morning-reports --max-tasks 5 --max-seconds 120
```

현재 마지막 명령은 0건을 처리한다. 기존 02:15 운영 예약과 별도이며 새 영구 서비스·스케줄은 배포하지 않았다.

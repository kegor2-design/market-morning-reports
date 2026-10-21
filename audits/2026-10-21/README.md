# MMP 운영 감사와 장기 시장 국면 예비 연구 — 2026-10-21

기준 시각: 2026-10-21 12:20~12:30 KST. 이 문서의 `확인`은 적힌 파일·쿼리·HTTP 응답으로 확인한 범위에만 적용된다. 운영 코드, cron, systemd, Blogger 게시물, PostgreSQL 데이터는 변경하지 않았다. MyDream2000은 읽기 전용 계정으로 스키마와 집계만 확인했다.

## 재현 자료

| 산출물 | 내용과 검증 방법 |
|---|---|
| [`build_audit.py`](build_audit.py) | 로컬 스냅샷을 읽어 아래 CSV·JSON 재생성. Python 표준 라이브러리만 사용 |
| [`sources.csv`](sources.csv) | 소스별 7·17·30일 시도와 성공. `raw/YYYY-MM-DD/collection_status.json`을 합산 |
| [`daily_pipeline.csv`](daily_pipeline.csv) | 10월 5~21일 일자별 수집, 이벤트, 보고서, 품질, 최종 MI 파일 및 스냅샷 일치 |
| [`metrics.json`](metrics.json) | 최근 누적 원시 기사 파일의 수집일 필터와 지연 시간, 이벤트 집계 |
| [`youtube_registry.csv`](youtube_registry.csv) | 실제 source registry의 YouTube 채널만 표시. 미확인 지표는 UNVERIFIED |
| [`dataset_inventory.csv`](dataset_inventory.csv) | 데이터셋별 제공처·기간·PIT·다운로드·검증 상태. 미확인은 명시적으로 표시 |
| [`monthly_drawdown_transitions.csv`](monthly_drawdown_transitions.csv) | 기존 공개 월간 지수의 고점 대비 낙폭 상태 전이. 검증된 조기경보가 아님 |

로컬 근거 경로: `MMPData/runtime/data/raw/`, `MMPData/runtime/data/normalized/`, `MMPData/runtime/data/state/`, `MMPData/reports/2026-10/`, `MMPData/logs/`, `MarketMorningPublisher/config/`, `MarketMorningPublisher/market_morning_publisher/market_history.py`, 이 저장소의 `market-history/data/`. 경로는 홈 디렉터리 기준이다. 원시 자료와 비밀 파일은 이 감사 폴더에 복제하지 않았다.

실행: `python3 audits/2026-10-21/build_audit.py`. 실측 실행 시간 9.33초, 최대 RSS 약 925 MB. 스크립트의 메모리 사용량은 97 MB 누적 기사 JSON 로드가 지배한다. 운영상 반복 주기 작업으로 사용하기 전에 스트리밍 파서를 적용해야 한다.

## 운영 환경

* 운영 소스: `MarketMorningPublisher`, 브랜치 `main`, 커밋 `ec273875f69ac9e36c7ac2c7e50413a170af474f`, remote `reports-source → kegor2-design/market-morning-reports`. 시작 시 다수의 기존 미커밋 변경이 존재하여 손대지 않았다.
* 결과 저장소: `market-morning-reports`, 브랜치 `main`, 시작 커밋 `45f134c289782c2a643b8d1d2926d69012cbf102`, 시작 상태 깨끗함.
* Python 3.12.3. MMP `data`, `logs`, `reports`, `youtube_sources`는 별도 MMPData 경로로 연결된다. `runtime/data`와 `research/youtube_sources`는 `/mnt/mydream_archive`의 심볼릭 링크다.
* 디스크: 94 GB 중 84 GB 사용, 가용 8.9 GB(91% 사용). RAM 3.8 GiB 중 약 2.6 GiB available, swap 8 GiB 중 약 97 MiB 사용. 샌드박스 `ps`에는 운영 프로세스가 표시되지 않아 실제 실행 여부는 미확인.
* cron과 systemd 상태 조회는 샌드박스 접근 제한으로 실패했다. 로그 파일의 최근 갱신은 스케줄 설정 자체의 증명이 아니다. `pg_isready -h 127.0.0.1 -p 5432`는 서버 권한에서 접속 가능을 반환했다. 기본 `kegor2` DB 역할은 없었다.
* 2026-10-21에 pipeline 로그 07:29, 장전 MI 로그 08:55, event poll 로그 12:20 KST 갱신 확인. 가장 최근 내부 장전 MI 최종 파일은 10월 21일 08:55이다.

## 뉴스 수집과 선별

`sources.csv`의 분모는 **소스 시도 횟수**이다. 10월 15~21일 490회 중 469회 성공(95.71%). 10월 5~21일 1,188회 중 1,133회 성공(95.37%). 각 날짜의 수집 스냅샷은 별개이지만, `items`는 그 시점의 피드 반환 건수여서 기간 신규 기사 수로 합산하면 안 된다. 소스별 `latest_item_lag_minutes`는 가장 최근 스냅샷 값이며 개별 기사 수집 지연과 다르다. `collector_name`과 신뢰도는 기록만으로 확정할 수 없어 공란/UNVERIFIED다.

30일은 2,098회 중 2,001회 성공(95.38%). 최근 7일 실패 21건은 세 소스가 매일 실패한 결과다: `event_calendar_fed_calendar`는 0행 건강성 검사 실패, `event_calendar_iea`와 `event_calendar_opec`는 HTTP 403. IEA는 해당 수집 상태에서 `required=true`, `severity=FAIL`로 표기된다. 나머지 소스의 성공은 내용 정확도나 원문 접근 성공을 뜻하지 않는다. 특히 10월 21일 `fed_press` 피드의 마지막 항목 지연은 6,200.1분으로 기록되어 `ok=true`만으로 신선도를 판정하면 안 된다.

최신 누적 원시 기사 파일에서 `collected_at`을 기준으로 최근 7일 10,294건, 30일 49,294건이 구분된다. 두 구간 모두 `article_id` 재출현은 0건이나 **사건 중복률은 이 값으로 측정할 수 없다**. 7일 중 발행·수집 시각이 유효한 10,192건의 지연 중앙값은 14.47시간, 24시간 초과는 1,596건(15.66%)이다. 음수 또는 30일 초과 지연은 중앙값에서 제외했다. `content_stored=true`는 두 구간 모두 0건이므로 기사 본문 접근 실패율, 본문 대 요약의 사실·숫자·조건부 표현 일치율은 계산할 수 없다.

10월 21일 정규화 이벤트 759건 중 `verified=true`는 168건, 출처 레코드가 2개 이상인 이벤트는 95건이다. 50개 이벤트는 출처 목록 내 같은 URL이 반복된다. 예: 캐나다 관세 소송 이벤트 `2d35a4046434bc5be13e2c62`에는 CNBC World/Markets 동일 URL과 BBC World/Business 동일 URL이 각각 이중 계상되어, 출처 레코드 4개를 독립 보도 4개로 간주할 수 없다. 보고서의 뉴스 선별은 이벤트 759건 중 60건으로 제한되었다. `raw → normalized → event → analysis → MI` 각 단계의 전체 입출력·제외 사유·원문 실패 로그는 일관된 개별 lineage 테이블이 없어 완전한 전환율을 검증하지 못했다.

대표 검토 후보: OpenDART `DART-20261020900775`는 원문 공시 URL이 연결된 국내 중요 사건, Reuters 금 시황 `3ede2393a36bb7abe4160a02`는 해외 일반 기사, 캐나다 관세 소송은 중복 출처 사례, 매일 IEA 403은 수집 실패 사례다. 이는 **링크·메타데이터 표본**이다. 원문 본문과 요약을 대조한 정확도 PASS 판정은 없다. 전망성 기사 `f9aaf9522fa4aa055fc596ea`도 공식 금리 결정으로 승격해서는 안 된다. 요약 실패 사례의 독립 분모 역시 없다.

중요 사건 누락 점검은 공식 발표 시간과 내부 기록을 분리했다. [BLS 2026년 10월 일정](https://www.bls.gov/schedule/2026/10_sched_list.htm)은 미국 9월 CPI를 10월 14일 08:30 ET, 9월 고용을 10월 2일 08:30 ET로 표시한다. 10월 15일 내부 이벤트에는 CPI 관련 제목 22건이 있으나 상위 60개 뉴스에는 BLS 원문 CPI 사건이 확인되지 않았다. 공식 일정·기사·캘린더·MI 간 완전한 링크 검사를 하지 못했으므로 `공식 발표 누락 확정`이 아니라 `수동 추적 필요`다. FOMC, 한국은행, 일본은행, 국채금리, 환율, 지정학, 반도체, 증시 정책, 기업 공시도 동일한 공식 원문 대조 표본이 필요하다.

## YouTube와 Chart Insight

실제 source registry에는 체슬리TV, AP투자연구소, 박종훈의 지식한방 3개 YouTube 소스가 `enabled=true`다. The Plain Bagel은 별도 과거 수집 파일이 있지만 이 registry의 등록 채널로 확인되지 않았다. 박세익 이름의 별도 채널도 확인되지 않았다. `youtube_registry.csv`의 최근 30일 운영 건수는 날짜별 영상 lineage를 확인하지 못해 미검증이다.

과거 수집 요약은 체슬리 2,857 처리 중 자막 2,848, 박종훈 346 시도 중 346 자막, Plain Bagel 266 시도 중 252 자막으로 기록한다. 이는 누적 요약 파일의 자기 보고이며 최근 30일율이나 발언 정확도는 아니다. 10월 15~21일 `state/nightly_youtube/*.json`에서 `claims_considered=0`, `chart_research.candidate_count=0`가 매일 확인된다. `normalized/youtube_insight/claims.jsonl`, `cards.jsonl`, `chart_insight/historical_validations.jsonl`은 0바이트다. Chart Insight `latest.json`은 2026-09-16 생성, `assessments_considered=0`, `validated=0`, `SHADOW_ONLY`다. 따라서 목록/자막(A~C)의 과거 일부 증거는 있지만 최근 발언 요약(D), 주장(E), 차트(F), 가격 검증(G), MI 반영(H)의 성공은 증명되지 않는다. 발언자, 발언 시각, 기간·전제·반대 시나리오, OCR 정확도 역시 미검증이다.

## 공개 Blogger와 장전 MI

10월 15~21일 Morning Data Report의 내부 publication URL 7개 모두 외부 HTTP HEAD 200을 확인했다. 10월 21일 [Morning Data Report](https://mmorningbriefing.blogspot.com/2026/10/morning-data-report-2026-10-21.html)와 [Premarket MI](https://mmorningbriefing.blogspot.com/2026/10/pre-market-mi-scenario-2026-10-21-0855.html)는 GET 200으로 본문을 받았다. 후자의 공개 본문에 내부 최종본의 `10월 19일 부분 지수`, `14.72%`, `수치 예측 보류`가 나타난다. 이 확인은 링크 생존 및 부분 문구 일치다. 전체 HTML 대 내부 Markdown의 내용 동등성, 깨진 외부 링크, 수치 원천 일치는 아직 PASS가 아니다. 과거 게시물은 수정하지 않았다.

`daily_pipeline.csv`는 10월 5~21일 상태표다. 10월 6·7·8·10일 `quality.passed=false`: 6·8·10일에는 `analysis_complete`, `frozen_identity_present`, `required_sections`, `semantic_quality` 등이 거짓이고, 7일에는 `calendar_event_gate=false`다. 10월 9일은 `DRY_RUN_READY`이므로 게시 성공으로 세지 않는다. 10월 11·17·18일은 `REPORT_PUBLISHED_MI_DEFERRED`이며 장전 최종 파일이 없다. 10월 12~16일과 19~21일은 최종 파일이 있고 최종본의 스냅샷 ID가 오전 MI의 ID와 일치한다. 10월 5일도 일치한다. 10월 21일 로그에는 최종 MI `PUBLISHED`와 Blogger URL이 기록된다. 즉 이전 `MORNING_PREMARKET_ARTIFACT_MISSING` 문제가 최신 10월 21일에도 지속된다고 볼 증거는 없다. 특정 과거 날짜의 파일 부재는 현재 파일 목록 기준이며 당시 API 재시도 실패의 직접 증거는 아니다.

원인 분류: 6·8·10일은 분석/필수 산출물/품질 게이트 복합 실패, 7일은 캘린더 게이트 실패가 직접 기록되었다. 11·17·18일은 내부 상태상 MI 보류이지만 주말 날짜이므로 장전 거래일 조건과 보류 정책의 관계를 추가 확인해야 한다. 수집 실패 3개와 MI 장애의 인과관계, Blogger API 실패, 게시 시각 오류, 파일 경로 불일치, 재시도 실패는 현재 증거로 확정할 수 없다. 권고: 출처별 필수 여부와 403 대체 공식 채널을 점검하고, 일자별 MI 생성·품질·게시 상태를 별개 구조화 로그로 남기며, 거래일/주말과 dry run을 대시보드에서 분리한다. 운영 설정 변경은 이 감사 범위에서 하지 않았다.

## 역사 데이터와 국면 정의

기존 `market-history/data/korea-market-monthly.csv`는 KOSPI 1996-11~2026-10 월간 360행, KOSDAQ은 2000-09부터 값이 있다. 생성 코드는 Yahoo Finance chart API의 1개월 간격 `close`를 사용한다. 2026-10은 진행 중인 월이다. 원본 공급자와 KRX 공식 종가 대조, 수집 시점별 불변 스냅샷, 이용 조건 검사가 없어 **지수 수준 자체를 검증 완료로 표기하지 않는다**. 10월 값은 역사적 확정 월말 관측치에서 제외해야 한다. 기존 `market-history/manifest.json`은 한국 지수 360행을 기록한다.

MyDream2000 PostgreSQL에는 `domestic_index_daily`가 813행(지수 코드 3개 × 271일), 날짜 2025-06-27~2026-10-20임을 읽기 전용 쿼리로 확인했다. `domestic_daily_price`, `domestic_investor_daily`, `us_market_daily`도 존재한다. PostgreSQL 통계의 추정 행 수는 각각 약 460만, 10.7만, 773이며 정확한 `count(*)`가 아니다. 네 테이블 전체 집계는 8초 statement timeout으로 중단되었다. MyDream2000 데이터는 이 저장소에 추출하지 않았다.

사전 정의한 **서술용 월간 상태**: 각 지수의 지금까지 최고 월간 `close` 대비 낙폭 `d=close/running_max-1`; `d≤-20%`는 `DRAWDOWN_20PCT`, `-20%<d≤-10%`는 `DRAWDOWN_10_TO_20PCT`, 나머지는 `OTHER`. 상태가 바뀌는 월만 CSV에 남긴다. 예: KOSPI 1997-09 -36.92%, 2008-06 -22.77%, 2022-05 -29.24%는 입력 파일 기준 계산 결과다. 이 정의는 하락 후에 알 수 있는 **동시 또는 지연 상태**이며 조기경보 모델이나 투자 신호가 아니다. 월간 자료로는 5·20·60·120거래일 선행 패턴, 이동평균·MACD·RSI·ADX·ATR·OBV 등 일간 기술 지표, 상승/횡보·거짓 경보의 precision/recall, walk-forward를 적법하게 계산할 수 없다. 월간 계산을 백테스트로 표시하지 않는다.

## 데이터 제공처 실사와 다음 검증 조건

| 데이터 | 제공처와 실제 확보 상태 | 관측 기간·주기 | Point-in-Time/재배포 |
|---|---|---|---|
| 한국 지수 월간 | Yahoo chart API 기반 기존 CSV 다운로드 기록, KRX 대조 미실시 | KOSPI 1996-11~, KOSDAQ 2000-09~; 월간 | 현재 CSV는 vintage 없음; 원자료 대량 재배포 보류 |
| 한국 일간 지수·종목·수급 | MyDream2000 PostgreSQL 존재만 확인, 원본 다운로드/공식 대조 미실시 | 지수 2025-06-27~2026-10-20; 일간 | `available_at` 열은 있으나 실제 공개 지연 검증 필요; 외부 공유 금지 |
| 미국 장기 주식 | 기존 Shiller CSV와 manifest, 공식 재검증 미실시 | 1871-01~2026-08; 월간 | 현행 데이터와 역사적 vintage 구분 필요 |
| 미국 CPI·금리 등 | 기존 FRED 경유 월간 CSV와 내부 보고서; 신규 다운로드 미실시 | 파일별 상이; 월간 | [FRED/ALFRED API](https://fred.stlouisfed.org/docs/api/fred/overview.html)의 실시간 기간과 vintage API를 별도 사용해야 PIT 가능 |
| 한국 CPI·국채금리 | 운영 코드가 ECOS API 키 기반 수집을 정의; 이번 실행에서 신규 다운로드 미실시 | 미검증 | 공개 시각, 수정 정책, 라이선스 조사 필요 |
| KRX 지수·수급·시장 폭 | [KRX 지수 안내](https://global.krx.co.kr/contents/GLB/02/0202/0202010101/GLB0202010101.jsp)에서 지수 제공 확인; 이번 실행에서 공식 다운로드 실패/미시도 구분상 **미시도** | 요구한 30년 일간 범위 미확보 | KRX 시장 데이터 재배포 조건 확인 필요 |
| OpenDART·FOMC·BoK·BoJ | 운영 수집기/소스 등록은 있으나 장기 PIT 데이터셋 신규 다운로드 미실시 | 미검증 | 원문 발표 시각과 정정 이력 보존 필요 |

장기 검증의 다음 조건은 KRX 공식 일간 KOSPI/KOSDAQ 및 거래량·거래대금 30년치 확보, 종목별 상장·상장폐지 이력 포함 시장 폭과 수급의 시점별 가용성, FRED/ALFRED vintage 및 한국 지표 최초 발표 시각 수집이다. 그 후 별도 연구 실행의 예상 자원과 저장 공간을 먼저 산정해야 한다. 현재 디스크 가용 8.9 GB와 RAM을 고려하면 수년치 원시 전종목 데이터의 무제한 다운로드는 적절하지 않다. 규칙 고정 → 기간 분리 → 순차 walk-forward → 급락과 정상 구간 모두의 거짓 경보 측정 순서로 진행해야 한다. 이번에는 데이터가 부족하여 precision, recall, FPR, lead time, 탐지 지연을 보고하지 않는다.

## 판정 경계

수집 `ok`, 이벤트 `verified`, 보고서 `quality PASS`, HTTP 200은 서로 다른 검사다. 각각 원문 진위, 요약 정확성, 게시 후 동일성, 시장 예측력을 증명하지 않는다. 7일 수집 성공률은 수집 엔드포인트의 건강도에 한정한다. 90일은 누적 원시 기사 파일만 기간 필터로 계산했으며, 90일 소스 시도율의 동일한 스냅샷 범위가 확인되지 않아 계산하지 않았다.

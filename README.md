# MarketMorningPublisher v1.2.1

MyDream2000과 분리된 뉴스·시장자료 수집기입니다. 검증된 입력을 Codex에 전달하고, `insight/OUR_MARKET_INSIGHT.md`의 **우리의 시장 인사이트**로 검토한 뒤 `insight/MORNING_BRIEF.md` 형식의 모닝브리핑을 만듭니다.

특정 투자자·투자사의 관점은 최종 판단 기준이 아닙니다. 새 관점은 먼저 후보로 검토하고, 채택한 내용만 버전이 있는 `MI-*` 원칙으로 추가합니다.

## 처리 구조

1. 공식기관·주요 언론사 직접 RSS를 우선 수집하고 뉴스 검색 RSS로 누락 보완
2. 시간 범위·관련성 필터, 중복 사건 군집화, 출처 검증
3. Yahoo Finance 완료 세션과 FRED 거시지표 수집
4. 검증 사건과 시장 데이터를 Codex에 JSON으로 전달
5. Codex 결과를 JSON Schema와 사건 ID로 재검증
6. 우리의 모닝브리핑 렌더링 및 품질검사

상시 감시 항목에는 미국 중간선거 정책, 중동·이란·호르무즈, 러시아·우크라이나,
미중·대만 핵심공급망, 유럽 방위·재정, 한반도·북한 및 국내 국무회의·비상경제점검회의가 포함됩니다.
국내 회의는 청와대 공개 브리핑 목록을 직접 수집하고 국무조정실·경제부처 공식 도메인 결과로 보완하며 최신 회의 결과를 7일간 유지합니다.
정책브리핑 RSS는 2026년 7월 1일 종료되어 수집 경로로 사용하지 않습니다.
직접 수집원과 검색 보완원은 각각 `direct`, `search`로 기록하며, 수집 상태에는 최신 항목의
게시 후 지연시간(`latest_item_lag_minutes`)을 남겨 소스별 속도를 비교합니다.
7. 모든 검사를 통과한 경우에만 GitHub·Blogger 발행

Codex 실행 실패, 스키마 위반, 존재하지 않는 사건 인용, 핵심 완료 세션 누락, 필수 거시지표 누락 중 하나라도 발생하면 종료코드 2와 `BLOCKED_QUALITY`가 기록되고 외부 발행은 차단됩니다. 기존 키워드 해석으로 자동 대체하지 않습니다.

## 설치

```bash
cd /home/kegor2
unzip MarketMorningPublisher_v1.2.1_codex_insight.zip
cd /home/kegor2/MarketMorningPublisher
chmod 750 ops/*.sh
cp .env.example .env
chmod 600 .env
python3 -m unittest discover -s tests -v
bash -n ops/*.sh
./ops/check_codex_ready.sh
```

Codex CLI에 이미 로그인했다면 그 인증을 재사용합니다. 서버 자동 실행에서 API 키 인증을 쓸 때만 `.env`의 `CODEX_API_KEY`를 설정합니다. Blogger·Git 인증값은 Codex 프로세스 환경으로 전달되지 않습니다.

## 첫 운영 검증

외부 발행 플래그를 모두 `0`으로 둔 뒤 실행합니다.

```bash
./ops/run_pipeline.sh /home/kegor2/MarketMorningPublisher /home/kegor2/MarketMorningPublisher/.env --dry-run --through-now
```

정규 모닝 구간으로 재검증하려면 `--through-now`를 뺍니다. `--skip-codex`는 수집기 진단 전용이며 분석과 발행은 반드시 차단됩니다.

결과 파일:

- `data/raw/YYYY-MM-DD/`: 원시 수집 결과와 출처 상태
- `data/normalized/YYYY-MM-DD-events.json`: 군집화·검증 사건
- `data/private/YYYY-MM-DD-codex-input.json`: Codex 입력 재현본(비공개)
- `reports/YYYY-MM/YYYY-MM-DD-outlook.json`: 분석·품질 상태
- `reports/YYYY-MM/YYYY-MM-DD-outlook.md`: 우리의 모닝브리핑

실서버에서 정상 분석 후 `quality.passed=true`, `analysis_meta.status=COMPLETED`를 확인합니다. 이후에만 `MMP_GITHUB_PUSH=1` 또는 `MMP_BLOGGER_PUBLISH=1`을 설정합니다.

## 자동 실행

```bash
./ops/install_cron.sh /home/kegor2/MarketMorningPublisher /home/kegor2/MarketMorningPublisher/.env
```

기본 cron은 주말·휴장일을 포함해 매일 08:10입니다. 서버 timezone이 KST가 아니면 crontab에 `CRON_TZ=Asia/Seoul`을 설정합니다.

- 거래일: 직전 거래일 15:30 이후부터 당일 08:10까지의 뉴스와 휴장일별 원시 수집본을 합쳐 누적 검토합니다.
- 거래일 모닝 브리핑은 이 구간에 새로 공개된 국내 공시·실적·수주·정책 뉴스를 별도 선별하고, 긍정·부정 산업과 다음 장 확인 조건을 함께 표시합니다.
- 장전 종목 관찰 후보는 비공개 국내 상장사 마스터와 검증된 가치사슬 노출도만 사용하며 `analysis.preopen_stock_candidates`를 `MMP_MYDREAM2000_PREOPEN_HANDOFF_V1` 계약으로 제공합니다. 장중 확정과 주문에는 사용하지 않습니다.
- 주말·휴장일: 직전 24시간 뉴스를 별도 `휴장일 뉴스 브리핑`으로 게시하고 원시 기사를 날짜별로 보존합니다.
- KRX 휴장일은 `config/market_holidays.json`에서 관리합니다. 거래소의 임시 휴장 공지가 있으면 이 파일에 날짜를 추가합니다.

## 장기 시장 지도

1871년 이후 Shiller S&P Composite 계열 월간 가격과 주요 역사 사건을 이용해 장기 로그 차트와 고점 대비 낙폭 차트를 생성합니다. 1957년 이전 구간은 현재 공식 S&P 500과 동일한 지수가 아니며, 가격지수에는 배당이 포함되지 않습니다.

```bash
./ops/run_market_history.sh /home/kegor2/MarketMorningPublisher /home/kegor2/MarketMorningPublisher/.env
./ops/update_market_history.sh /home/kegor2/MarketMorningPublisher /home/kegor2/MarketMorningPublisher/.env
./ops/install_market_history_cron.sh /home/kegor2/MarketMorningPublisher /home/kegor2/MarketMorningPublisher/.env
```

주간 갱신 cron은 토요일 07:20 KST에 실행됩니다. 생성 결과는 `public/market-history/`에 저장되고 공개 보고서 저장소와 Blogger의 `Market History | 장기 시장 지도` 고정 페이지가 갱신됩니다. 원본 Excel 파일은 `data/private/`에만 보관합니다.

## 인사이트 변경

- 현재 원칙(유일한 해석 기준): `insight/OUR_MARKET_INSIGHT.md`
- 브리핑 구성: `insight/MORNING_BRIEF.md`
- Codex 출력 계약: `config/codex_analysis_schema.json`

원칙을 추가·수정할 때는 `MI-*` 버전, 적용 조건, 반증 조건을 함께 바꾸고 JSON Schema의 허용 원칙 ID 및 테스트도 갱신합니다. 불투명한 종합 점수나 인물 이름을 판단 근거로 추가하지 않습니다.

## 보안·저작권

- `.env`, OAuth token, API key, 원문 HTML은 결과·Git·배포 ZIP에 포함하지 않습니다.
- `data/private/reference/korea_equity_master.json`은 MyDream2000의 읽기 전용 `symbol_master_trade_eligible_v`에서 생성하는 비공개 스냅샷입니다. `scripts/export_mydream2000_equity_master.py`로 갱신합니다.
- `data/private/reference/korea_equity_reference.sqlite3`은 DART 기업번호·사업보고서·가치사슬 근거의 기준 DB입니다. `scripts/build_korea_equity_reference_db.py`로 전체 종목을 매핑하고 `scripts/enrich_dart_equity_exposures.py --symbols ...`로 후보 기업을 증분 수집합니다.
- 전체 수집은 `scripts/run_dart_exposure_batch.py`가 재시작 가능한 진행 파일을 기록하며 수행합니다. 분류표 변경 후에는 `scripts/reindex_dart_exposure_cache.py`로 저장된 공시 원문을 다시 색인하고, `scripts/audit_korea_equity_reference_db.py --require-complete`로 모집단 커버리지와 무결성을 검사합니다.
- 가치사슬 분류표는 `config/korea_value_chain_taxonomy.json`에 있으며 제품·서비스, 원재료 의존, 고객시장, 계열사, 단순 언급을 분리합니다. 제품별 매출 비중은 공시에 수치 근거가 있고 검증된 경우만 기록하며 추정값은 넣지 않습니다.
- 사업보고서 키워드 발견은 즉시 후보에 사용하지 않습니다. `scripts/review_dart_equity_exposures.py`로 검토한 `VERIFIED` 항목만 `config/korea_equity_exposures.json`에 내보내 장전 후보 생성기가 참조합니다.
- 공개 결과에는 제목, 링크, 짧은 제공 요약, 자체 분석만 둡니다.
- Codex는 읽기 전용·임시 세션으로 실행하며 입력 JSON을 명령으로 취급하지 않습니다.
- 유료 원문 크롤링, 무단 재게시, MyDream2000 DB 연결은 포함하지 않습니다.
- 결과는 정보 정리와 연구용이며 투자 권유가 아닙니다.

# KOSPI·KOSDAQ 일간 데이터 수집 및 KRX 교차검증 — 2026-10-21

## 실제 실행 결과

2026-10-21 KST에 Yahoo Finance chart API와 네이버 금융 차트에서 일간 OHLCV를 실제 다운로드했다. 요청 종료일은 **2026-10-20**이며 미래일·진행 중인 10월 21일 장은 저장하지 않았다. 기존 `market-history/data/` 및 MarketMorningPublisher 운영 코드는 변경하지 않았다. 시작 시 디스크 가용 공간은 8.8 GB였다. 전체 연구 폴더는 약 5 MB다.

| 지수 | 네이버 유효 행·기간 | Yahoo 유효 행·기간 | 양쪽 종가 대조 | 0.01포인트 이내 일치 | 불일치 | KRX 공식 대조 | 판정 |
|---|---:|---:|---:|---:|---:|---:|---|
| KOSPI | 7,730; 1996-01-03~2026-10-20 | 7,347; 1996-12-11~2026-10-20 | 7,347 | 7,335 (99.8367%) | 12 | 0 | **FAIL** |
| KOSDAQ | 7,574; 1996-07-02~2026-10-20 | 6,408; 2000-10-16~2026-10-20 | 6,408 | 6,407 (99.9844%) | 1 | 0 | **FAIL** |

`FAIL`은 보조 공급자 사이 종가 검증 실패와 네이버 OHLC 자체 모순이 실제 확인되었기 때문이다. 어느 공급자 값이 정답인지는 KRX 공식 자료가 없어 판단하지 않았다. **KRX 교차검증 상태는 두 지수 모두 UNVERIFIED**다. 보조 공급자 간 높은 일치율을 KRX 공식 일치율로 해석하면 안 된다. 공식 일치율·공식 최대 오차는 **계산 불가**이며 성공 0건, 실패 0건, 미검증 전체다.

## 출처, 보관, 재현

- 네이버: `https://fchart.stock.naver.com/sise.nhn?symbol=KOSPI`와 `symbol=KOSDAQ`, `requestType=1`, `startTime=19960101`, `endTime=20261020`, `timeframe=day`. 네이버 응답은 KOSPI 1996-01-03, KOSDAQ 1996-07-02부터 반환했다. 이 출처의 공식 KRX 원본 여부는 확인되지 않았다.
- Yahoo: `https://query1.finance.yahoo.com/v8/finance/chart/%5EKS11` 및 `%5EKQ11`, `period1=820454400`, `period2=1792540800`, `interval=1d`. 가격 없는 휴장일 모양의 행 KOSPI 149건, KOSDAQ 85건을 유효 시세 건수에서 제외했다. 원본 JSON은 그대로 로컬에 보관했다.
- 수집 시각(UTC), URL, 원본·정규화 CSV의 SHA256 및 크기는 [`source_manifest.json`](source_manifest.json), [`naver_source_manifest.json`](naver_source_manifest.json)에 있다. 원본 파일은 이 서버의 `market-morning-reports/market-history/research/daily-index-validation-20261021/`에 보관한다. 원본 전체와 전일 시세 CSV는 가격 데이터 재배포 권한을 확인하지 못해 GitHub에 게시하지 않았다. Yahoo의 [서비스 약관](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)은 데이터 기반 대체 데이터베이스·피드 제공을 제한한다. 재현 시 아래 스크립트가 동일 경로에 새 스냅샷을 저장하므로 **원본 SHA가 달라질 수 있다**.
- [`collect.py`](collect.py), [`collect_naver.py`](collect_naver.py)가 수집기, [`validate.py`](validate.py)가 표준 라이브러리만 이용하는 검증기다. 수집기는 외부 `requests` 패키지가 필요하다.

## 검증 기준과 발견 사항

종가는 같은 거래일의 양쪽 값 차이가 **0.01 지수 포인트 이하**면 일치로 보았다. Yahoo의 이진 부동소수점 표기를 위해 계산상 0.0101을 사용했다. 상대 오차는 `절대 오차 / 네이버 종가 × 100`이다. 최댓값은 KOSPI 1999-01-05 **21.769971포인트**, KOSDAQ 2001-11-01 **10.900024포인트**였다. 불일치 날짜와 두 값은 [`provider_mismatches.csv`](provider_mismatches.csv)에 있다. 이는 KRX 검증이 아니다.

| 검사 | KOSPI | KOSDAQ | 해석 |
|---|---:|---:|---|
| 네이버/야후 중복 날짜 | 0/0 | 0/0 | 각 유효 시세 CSV 내부 |
| 네이버 OHLCV 자체 모순 | 4 | 1 | KOSPI 1996-06-12, 1996-08-17, 2003-10-27, 2007-03-02; KOSDAQ 2007-03-02 |
| Yahoo OHLCV 자체 모순 | 0 | 0 | Yahoo 제공 구간에 한정 |
| 네이버 일간 절대 수익률 15% 초과 | 1 | 0 | KOSPI 2026-07-31 +17.91%; 양쪽 공급자 값 일치, 진위 별도 확인 필요 |
| Yahoo가 네이버 세션에 유효 가격 미제공 | 104 | 5 | KOSPI 97건은 1998년까지의 토요일, 7건은 평일. KOSDAQ 5건은 평일 |
| Yahoo 시작 전 네이버 세션 | 279 | 1,161 | Yahoo 공급 범위 차이, 거래일 누락으로 집계하지 않음 |
| 네이버 간격 중 평일 3일 이상 공백 후보 | 36 | 36 | 공휴일 가능성 있음. 공식 거래일 달력 미확보로 누락 확정 불가 |
| 거래대금 | 전 기간 미제공 | 전 기간 미제공 | 거래량 단위와 산출 범위도 공식 검증 전 |

`daily_data_quality_report.csv`에는 날짜별 자체 모순·급변·공급자 불일치·Yahoo 누락·달력 공백 후보 및 집계를 기록했다. **네이버에도 빠진 실제 거래일**은 공식 거래일 달력 없이는 탐지할 수 없다. 2007-03-02 네이버의 종가는 있지만 시가·고가·저가가 0이라 OHLCV 백테스트에는 그대로 사용할 수 없다. 가격 오류를 임의 보간하거나 한 제공처 값으로 덮어쓰지 않았다.

1997~1998 외환위기, 2000~2001 IT 붕괴, 2008~2009 금융위기, 2020 코로나, 2022 금리 인상기, 2025~2026의 각 공급자 대조 건수와 실패 건수는 [`historical_window_summary.csv`](historical_window_summary.csv)에 있다. 특히 1997~1998 KOSDAQ은 Yahoo 제공 시작 전이라 보조 대조도 0건이다. KOSDAQ은 2004-01-26 기준 지수가 100에서 1,000으로 변경되어 과거치에 소급 적용된 계열로 보인다. 이 변경은 [당시 보도](https://news.sbs.co.kr/news/endPage.do?news_id=N0311531792)와 [한국민족문화대백과사전](https://encykorea.aks.ac.kr/Article/E0068518)에 기술된다. 원시 당시 발표값과 소급 계열을 혼용하지 않아야 한다.

## KRX 공식 자료 접근 결과

KRX Data Marketplace의 `MDCSTAT00301` 개별지수 시세 요청을 2020-10 한 달의 KOSPI 표본으로 실제 보냈다. 비로그인 POST는 **HTTP 400, `LOGOUT`**이었다. 메인 페이지 GET으로 세션 쿠키를 받은 뒤 같은 세션의 POST도 **HTTP 400, `LOGOUT`**이었다. [`krx_access_attempts.json`](krx_access_attempts.json)에 파라미터와 응답을 기록했다. [KRX 로그인 페이지](https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc)는 계정 로그인을 요구한다. [KRX Open API 서비스 목록](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd)의 시계열은 2010-01-04 이후 제공으로 명시돼 있으며, 현 환경에 API 키는 없다. 1996~2009 공식 원본은 별도 경로가 필요하다.

[`krx_daily_comparison.csv`](krx_daily_comparison.csv)는 스키마만 있으며 **데이터 행 0건**이다. 공식 가격을 확보하지 못했으므로 임의로 채우지 않았다. 다음 조치는 KRX 인증 계정 또는 허가된 공식 추출본을 확보하고 2010년 이후를 전체 교차검증한 뒤, 1996~2009의 공식 역사 자료 및 거래일 달력을 별도로 구하는 것이다. 공개 게시 가능 여부도 공급자와 확인해야 한다.

## 산출물과 사용 판정

- [`daily_index_data_inventory.csv`](daily_index_data_inventory.csv): 지수별·출처별 유효 건수, 기간, 공식 검증 상태.
- [`krx_daily_comparison.csv`](krx_daily_comparison.csv): 공식 대조 스키마, 데이터 행 0건.
- [`daily_data_quality_report.csv`](daily_data_quality_report.csv): 누락·중복·이상치·단절 후보·미확인 항목.
- [`provider_mismatches.csv`](provider_mismatches.csv): 보조 제공처 간 실제 종가 불일치 13건.
- [`historical_window_summary.csv`](historical_window_summary.csv): 지정 위기 구간별 대조 범위.

**30년 급락 조기경보 백테스트의 검증된 입력으로는 사용 불가.** 공식 종가·거래일 검증이 0건이고 불일치 및 자체 모순이 남아 있다. 연구용 탐색에는 출처·날짜별 품질 플래그를 유지해야 하며, 현재 파일을 확정 가격 또는 시점별 최초 발표 자료로 취급해서는 안 된다.

## 실제 실행 명령

```text
df -h /home/kegor2                                      # 가용 8.8 GB
python3 market-history/research/daily-index-validation-20261021/collect.py
python3 market-history/research/daily-index-validation-20261021/collect_naver.py
python3 market-history/research/daily-index-validation-20261021/validate.py
```

첫 네이버 실행은 EUC-KR XML 인코딩 처리 오류로 종료됐고, 디코딩을 수정한 뒤 재실행해 성공했다. 최종 검증기는 KOSPI 7,347건·KOSDAQ 6,408건의 보조 종가 대조 및 각각 12건·1건의 차이를 출력했다. 운영 코드·MI 규칙·MyDream2000 환경은 수정하지 않았다.

# 해외 선행지표 경로·PIT 연결 감사 — 2026-10-22

**결론: 연준 H.15 미국 2년·10년 금리만 발표 시각 기준으로 연결했다.** 현재 제공되는 역사 파일은 최초 발표값(vintage) 검증이 끝나지 않아 백테스트는 탐색 결과다. 고정 금리 충격 규칙은 v2 `DD20_5` 대비 최종 기간의 사건 포착률 또는 오경보를 함께 개선하지 못했다. Cboe VIX, 미국 지수, USD/KRW는 모델에 넣지 않았다.

## 실제 자료 범위와 사용권

|자료|확인한 관측 범위|2010-01-01~2026-10-20 결측|사용 판단|
|---|---|---:|---|
|미국 2년 국채금리 (DGS2)|1976-06-01~2026-10-19|평일 4,382행 중 181행 (4.13%)|연준 H.15 공식 CSV를 로컬 사용. FRED 표시는 공공영역·출처표기 요청.|
|미국 10년 국채금리 (DGS10)|1962-01-02~2026-10-19|평일 4,382행 중 181행 (4.13%)|동일|
|VIX (VIXCLS)|1990-01-02~2026-10-20|**실측 불가**|Cboe 공개 페이지는 1990년 이후 일간 종가 링크를 제공하지만 사이트 약관상 비개인 연구·저장·다른 데이터 검증에는 사전 서면 허가가 필요하다. FRED는 저작권·출처표기 자료로 표시한다. 현 작업에서는 사용권을 확정하지 못했고 FRED CSV도 유지보수 페이지를 반환해 관측치를 받지 못했다.|

금리의 결측률 분모는 연준 공식 CSV에 있는 **미국 평일 행**이며 한국 거래일 분모와 다르다. 연준 CSV의 전체 역사 값은 로컬 `h15_rates.local.csv`에만 보관하고 GitHub에 게시하지 않았다. 해당 자료의 SHA-256, 관측치 수와 날짜는 `metrics.json`, `source_coverage.csv`, `external_source_inventory.csv`에 기록했다. [FRED DGS2](https://fred.stlouisfed.org/series/DGS2), [DGS10](https://fred.stlouisfed.org/series/DGS10), [연준 H.15 공식 다운로드](https://www.federalreserve.gov/datadownload/choose.aspx?rel=h15), [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS), [Cboe VIX 역사 페이지](https://www.cboe.com/tradable_products/vix/vix_historical_data), [Cboe 이용 약관](https://www.cboe.com/terms), [Cboe 콘텐츠 허가 절차](https://www.cboe.com/use-of-content), [FRED 이용 조건](https://fred.stlouisfed.org/legal/terms/)을 근거로 했다.

## 미국 증시·환율 확보 경로

- **S&P 500:** [S&P DJI 공식 데이터 라이선스](https://www.spglobal.com/spdji/en/about-us/data-index-licensing/) 또는 허가된 유통사. 일간 종가, 수정 이력, 내부 연구·운영 사용 범위, 외부 성능 공개 범위를 계약에 명시해야 한다.
- **NASDAQ Composite·PHLX SOX:** [Nasdaq GIDS](https://www.nasdaq.com/products/global-indexes/data/gids) 또는 Nasdaq 허가 유통사. 2010~2026 일간 종가와 당시 공개 시각·수정 이력 제공 여부를 확인해야 한다. Nasdaq의 [일간 지수 데이터 제품](https://data.nasdaq.com/databases/NEID/documentation?anchor=eod-index-values-ndaq-eiv-)은 과거 값의 재작성 내역을 포함한다고 설명한다.
- **USD/KRW:** [연준 H.10 한국 원화 역사 자료](https://www.federalreserve.gov/releases/h10/hist/) 또는 [FRED DEXKOUS](https://fred.stlouisfed.org/series/DEXKOUS). 이는 뉴욕 정오 호가이며 한국 장중 현물환 종가와 같은 정의가 아니다. H.10은 전주 일간 값을 다음 주 월요일 동부시간 16:15에 게시한다. [과거 발표본](https://www.federalreserve.gov/releases/H10/About.HTM)은 미수정 상태로 보관되므로 진정한 최초발표 PIT 구성에 적합한 경로다. 2026년 8월에도 [H.10 정정 공지](https://www.federalreserve.gov/feeds/H10.html)가 있었으므로 현재 역사 파일을 당시 값으로 사용해서는 안 된다.

이 경로들에서 원시 시세를 다운로드하거나 재배포하지 않았다. MMP 설정에 VIX·금리·미국 지수·환율 식별자가 있는 것과 장기 PIT 관측치가 실제로 보관된 것은 별개다.

## H.15 발표 시각 연결

연준은 [H.15를 미국 동부시간 16:15에 매 영업일 게시](https://www.federalreserve.gov/releases/h15/)한다. 예를 들어 2026-10-20 발표본에는 2026-10-19 수익률이 실린다. 각 관측일 `d`에는 그 **다음 H.15 정상 발표일 16:15**를 붙여 UTC로 변환했다. 한국 거래일의 확정 종가 후 18:00 KST에 이르기 전 발표된 값 중 가장 최근 값만 연결했고, 관측일이 7달력일보다 오래되면 결측 처리했다. 5일 변화량은 5개의 **서로 다른 H.15 관측치** 사이에서 계산했다. 경보 대응은 한국 다음 거래일이다. 미국 휴일과 서머타임은 공식 CSV의 날짜 및 `America/New_York` 시간대 변환으로 처리했다.

2010~2026 한국 거래일은 지수별 4,133일이며, 금리 발표 시각 연결은 각각 4,133일 성공·미연결 0일·미래 발표 참조 0건이다. 연결 값의 최대 관측 연령은 5달력일, 중앙값은 2일이다. 2010-01-04 한국 장 마감에는 2009-12-30 미국 관측치를, 2026-10-20 장 마감에는 2026-10-16 관측치를 연결한다. 일별 날짜·발표 시각·금리 값을 담은 `pit_join.local.csv`는 **비공개 로컬**로만 생성한다. 집계는 `pit_join_audit.csv`에 있다.

**PIT 한계:** 연준 H.15 공식 다운로드는 현재의 역사 스냅샷이다. [연준의 과거 정정 공지](https://www.federalreserve.gov/feeds/h15.html)는 일부 금리 관측치가 사후 수정됐음을 보여준다. 매 경보일의 최초 발표본 또는 ALFRED vintage를 대조하지 못했으므로 `vintage_verified=0`으로 기록했다. [FRED/ALFRED API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)의 vintage 조회에는 별도 API 키가 필요하다. 따라서 이 연결표는 **발표 시각 PIT 후보**이며 완전한 최초 발표값 PIT 자료라고 주장하지 않는다.

## 동일 사건·기간 탐색 평가

v2의 KRX 종가 SHA, 60일 고점 대비 최초 -10% 사건과 병합 규칙, 개발(2010~2017)·검증(2018~2021)·최종(2022~2026) 기간 및 에피소드 평가 함수를 그대로 썼다. `DD20_5` 결과가 각 기간에서 v2 `metrics.json`과 정확히 일치함을 코드에서 확인한다. 네 규칙은 사전에 고정했고 임계값을 최종 기간에서 고르지 않았다.

|규칙|정의|
|---|---|
|DD20_5|v2 기준선|
|H15_SHOCK_25BP|2년 또는 10년 금리의 5개 H.15 관측치 변화 절댓값 ≥ 0.25%p|
|DD20_5_AND_H15|두 신호 동시 발생|
|DD20_5_OR_H15|어느 한 신호 발생|

|최종 2022~2026|사건 포착|에피소드 적중/전체|오경보 에피소드|선행 중앙값|
|---|---:|---:|---:|---:|
|KOSPI DD20_5|9/9|21/44|23|13일|
|KOSPI H15_SHOCK_25BP|4/9|6/65|59|8.5일|
|KOSPI DD20_5_AND_H15|4/9|5/23|18|3.5일|
|KOSPI DD20_5_OR_H15|9/9|22/80|58|13일|
|KOSDAQ DD20_5|7/7|13/57|44|10일|
|KOSDAQ H15_SHOCK_25BP|3/7|5/65|60|14일|
|KOSDAQ DD20_5_AND_H15|2/7|3/27|24|10일|
|KOSDAQ DD20_5_OR_H15|7/7|12/91|79|10일|

금리 필터는 오경보를 줄이는 대가로 사건을 크게 놓쳤고, OR 규칙은 사건 포착을 유지하는 대신 오경보를 늘렸다. 이 고정 규칙들에서 **유효한 성능 기여는 확인되지 않았다.** 개발·검증·최종 상세 지표와 WF1~WF4는 `model_comparison.csv`, `walkforward_results.csv`, `metrics.json`에 있다. vintage 검증이 끝나기 전에는 통계적으로 유의한 개선·악화를 운영 근거로 삼지 않는다.

## 재현 및 다음 단계

서버의 비공개 KRX 검증 종가와 공식 H.15 로컬 파일이 있는 상태에서 `python3 market-history/research/krx-crash-warning-external-20261022/run.py`를 실행한다. 출력은 모두 신규 생성 전용이며 기존 파일을 덮어쓰지 않는다. `python3 test_run.py`는 미래 발표 참조와 경계 사례를 검사한다. GitHub에는 로컬 원시 금리·KRX 시세·연결 값·비밀정보를 올리지 않는다.

다음 단계는 (1) H.15 최초 발표값 정정 감사, (2) Cboe/FRED VIX 자료의 해당 연구·운영 사용권과 일별 결측 확인, (3) H.10 발표본으로 환율 최초 발표값 연결, (4) 허가된 미국 지수 데이터의 시각·수정 이력 확보, (5) 동일 사건 표본 비교다. 그 뒤에만 국내 수급·breadth를 추가한다. 이 단계 전까지 MMP 운영 MI 규칙과 MyDream2000에는 반영하지 않는다.

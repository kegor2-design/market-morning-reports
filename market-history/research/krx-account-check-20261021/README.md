# 기존 KRX 계정으로 일간 지수 공식 교차검증 — 2026-10-21

## 실행 결과

MMP의 `structural_flow.PykrxProvider`가 사용하는 PyKRX 인증 구현을 조사했다. PyKRX는 모듈 로드 시 `KRX_ID`·`KRX_PW`로 KRX Data Marketplace 웹 세션을 만들며, 로그인 페이지 준비 요청 후 `MDCCOMS001D1.cmd`로 로그인한다. 이번 연구 실행은 그 기존 로그인 흐름을 한 번 사용했다. 로그인 응답은 **HTTP 200 / `CD001`(성공)**이었다. 이후 `MDCSTAT00301`에 2020-10-05~2020-10-09 범위의 KOSPI(`1001`)와 KOSDAQ(`2001`)을 각 한 번 요청했고, 두 응답 모두 **HTTP 200**이었다. 실제 공식 종가를 각 4거래일, 합계 **8행** 받았다. [상태 기록](result.json)에는 비밀정보, 쿠키, 원문 응답을 넣지 않았다.

| 날짜 | KOSPI 공식 종가 대조 | KOSDAQ 공식 종가 대조 |
|---|---:|---:|
| 2020-10-05 | 네이버·Yahoo 모두 일치 | 네이버·Yahoo 모두 일치 |
| 2020-10-06 | 네이버·Yahoo 모두 일치 | 네이버·Yahoo 모두 일치 |
| 2020-10-07 | 네이버·Yahoo 모두 일치 | 네이버·Yahoo 모두 일치 |
| 2020-10-08 | 네이버·Yahoo 모두 일치 | 네이버·Yahoo 모두 일치 |

기존 [`daily-index-validation-20261021`](../daily-index-validation-20261021/README.md)의 날짜별 자료와 **공식 종가 8행 × 기존 공급자 2곳 = 16건**을 비교했다. 허용 오차는 기존 검증과 같은 0.0101 지수 포인트이며 **불일치 0건**, 최대 관찰 오차 0.00포인트였다. 공식 종가와 날짜별 수치 비교는 서버의 `comparison.local.csv`에만 저장했다. 시세 재배포 권한이 확인되지 않아 GitHub에는 전체 가격 행을 게시하지 않는다. 재현 코드는 [`check.py`](check.py)다.

## 미검증 범위

이번 조회는 2020-10-05~2020-10-08의 4거래일에 한정된다. 기존 자료 중 KOSPI 네이버 **7,726/7,730행**, Yahoo **7,343/7,347행**, KOSDAQ 네이버 **7,570/7,574행**, Yahoo **6,404/6,408행**은 공식 종가와 아직 비교하지 못했다. 따라서 KOSPI의 **1996-01-03~2026-10-20**, KOSDAQ의 **1996-07-02~2026-10-20** 범위에서 이 4일을 제외한 기간이 미검증이다. 해당 기간의 불일치 건수는 0이 아니라 **미확인**이다. 공식 거래일 달력과 OHLCV도 검증하지 않았다. 기존 자료는 덮어쓰지 않았다.

## 웹 로그인과 Open API

이번 성공은 KRX **Data Marketplace 웹 세션**의 `MDCSTAT00301` 조회를 뜻한다. [KRX Open API KOSPI](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES001_S2.cmd?BO_ID=EREKZauXnMmxyIlqzeDN)와 [KOSDAQ](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES001_S2.cmd?BO_ID=nimebcamqFNIPNcRrHoO)는 별도 `AUTH_KEY` 헤더 및 각 API 이용신청을 안내한다. 현재 MMP 환경에는 해당 API 키가 확인되지 않았다. 웹 로그인 성공을 Open API 이용 승인으로 취급할 수 없다. [KRX 서비스 목록](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd)에 따르면 Open API의 이 지수 시계열은 2010-01-04부터 제공되므로, 1996~2009년의 공식 검증에는 별도 역사 자료가 필요하다.

첫 실행은 샌드박스의 DNS 차단으로 KRX HTTP 응답을 받기 전에 중단됐다. 허용된 네트워크에서 정상 로그인과 표본 조회가 성공했으므로 계정 인증 실패는 관찰되지 않았다. 별도의 실패 로그에 계정 값이나 서버 원문을 저장하지 않았다.

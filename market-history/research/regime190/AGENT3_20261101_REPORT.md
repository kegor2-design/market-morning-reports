# Regime190 Agent 3.0 연구 기록 (2026-11-01)

## 범위와 출발점

- 분리된 연구 작업 트리: `/home/kegor2/market-morning-reports-agent3`; 출발 커밋 `09778943f57a739528fb01a7009cd0efda6020a6` (기존 Agent 2.0/자동 진단 브랜치).
- 기존 운영 연구 경로 `/home/kegor2/market-morning-reports`는 `2c7f79e`의 별도 브랜치이며 02:15 크론은 그 경로를 참조한다. 해당 경로 및 `MyDream2000`, `MarketMorningPublisher`는 수정하지 않았다.
- 이전 검증 기준: 작업 큐, 체크포인트, 메모리, 합성 테스트, Regime190 탐색 백테스트 및 자동 진단. 변경 전 Regime190 33개와 universal_agent 54개 테스트 통과.

| 구성 요소 | 현재 구현 및 확인 | 재사용/추가 | 위험과 통제 |
| --- | --- | --- | --- |
| Agent 2.0 작업 큐·의존성·체크포인트 | VERIFIED, 기존 `offline_worker` | 동일 큐에 Agent 3.0 허용 목록 어댑터만 추가 | 기존 54개 회귀 테스트 |
| 연구 메모리·중복 방지 | VERIFIED, 기존 원자적 저장·잠금 | 산출물/코드/원본 CSV 해시와 체크포인트를 재개 시 비교 | 변조 시 즉시 실패 |
| Regime190 지표·PIT 차단 | VERIFIED, 190개 중 PIT 승인 0개 | 190개 차단 이유와 DB 표본 조사 | 승인 자동 승격 금지 |
| 탐색 백테스트·기준선 | VERIFIED, 실제 지수 스냅샷 기반 | 동일 원본/비용/다음 세션 체결 규칙으로 비교 | 공식 실적 주장 금지 |
| 자동 진단 | VERIFIED, 이전 7개 진단 | 진단 근거 기반 고정 실험 두 개 연결 | 원인과 상관관계 분리 |
| 모델 추론·임의 코드 수정 | NOT_IMPLEMENTED | 검토된 고정 템플릿만 실행 | 모델 없음, 동적 코드 실행 없음 |

## 원본 결과 재현 및 진단

이전 원본 JSON과 메모리 해시, 지수 CSV 해시를 검사하고 기존 진단기를 다시 실행했다. 원본의 4,052거래일(2010-03-31~2026-09-15) 결과는 탐색 결과이며 PIT 승인 성과가 아니다.

| 관찰 | 재현 수치 | 해석 범위 |
| --- | --- | --- |
| 20일 하락 경고 | TP 51, FP 621, FN 159, TN 3221; 정밀도 7.59%, 재현율 24.29%, 양성 비율 5.18% | 희귀 사건과 경고 과다의 연관성은 관찰. 인과 원인 확정 불가 |
| 같은 기간 변동성 기준선 | 정밀도 30.57%, 재현율 28.10% | 기존 경고의 추가 예측 가치 입증 실패; 사건 창 중첩/PIT 미검증 |
| 회복 신호 | TP 2, FP 36, FN 87; 정밀도 5.26%; 38신호 중 15일은 신호와 결과의 낙폭 적격 기준 불일치 | 라벨 불일치 및 표본 부족 확인. 낮은 정밀도의 전체 인과 설명은 미확정 |
| 여섯 국면 전략 | 누적 수익 34.93% 대 매수 보유 299.28%; 로그 자산 격차 1.0849 중 기회비용 0.7548, 거래 비용 격차 약 0.3301 | 로그 자산 항등 분해이며 인과 귀속 아님 |

## PIT 및 데이터 조사

지표 190개: `PIT_BLOCKED` 71, `CALCULATION_PENDING` 21, `SOURCE_MISSING` 98, `PIT_VERIFIED` 0. 이전 근거 목록의 출판 시각 및 개정 이력 미검증 190개, 과거 구성 종목 66개, 기업행위 32개 문제를 유지했다. 직접 DB 조회는 실제 `information_schema.columns` 확인 후 읽기 전용 트랜잭션, 5초 타임아웃, 테이블당 최대 20행으로 제한했다. 과거 가격 표본 20행의 market가 공란이며 `available_at` 16:30은 수집 전의 내부 시각일 뿐 원본 발표 시각의 독립 증거가 아니다. 최근 금리 표본 20행은 `released_at`과 `vintage_date`가 모두 공란이었다. **PIT 승격 0개.** 누락된 메타데이터만으로 자료 전체의 과거 사용 불가능을 단정하지 않는다.

[KRX 공식 API 목록](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd)은 2010년 이후 KOSPI/KOSDAQ 일별 시계열의 후보이고, [KRX 전송 시각 안내](https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA002.jsp)는 일반 종가 자료 전송 시각의 후보 근거다. 개별 과거 행의 발표 시각과 이용 권한은 추가 확인이 필요하다. [FRED 관측치 API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)의 빈티지 기능도 시리즈별 발표 시각 확인을 대체하지 않는다. 새 데이터 다운로드나 유료 서비스 사용은 수행하지 않았다.

## 통제된 연구 실험과 자동 재시도

1. `recovery_label_alignment_v1`: 신호를 고정하고 회복 결과의 낙폭 적격 조건만 -10%에서 -8%로 변경. 훈련 1,896일: 신호 14, 기존/변경 양성 16/20, TP 모두 0. 검증 986일: 신호 6, 양성 28/29, TP 모두 0. 결과 정의를 바꾼 수치이므로 성능 개선 비교는 **NONCOMPARABLE_MEASUREMENT_REPAIR**. 이 실패를 메모리에 기록하고 다음 가설을 자동 선택했다.
2. `regime_hysteresis_v1`: 국면 전환을 제안 국면 2일 연속 확인으로 제한. 원본·노출표·거래 비용 0.15% 편도·다음 세션 시가 체결 규칙을 유지. 훈련의 기준선/후보 누적 수익 -10.87%/+0.56%, 샤프 -0.157/+0.049, 편도 회전 88.5/47.5. 이전에 살펴본 검증 구간의 누적 수익 10.72%/13.34%, 샤프 0.318/0.375, 회전 59.25/31.25. 20거래일 간격의 7개 탐색 시계열 폴드 중 후보 샤프가 높은 구간은 4개, 낮은 구간은 3개다. 편도 비용 0.05%에서는 후보 누적 수익 16.94%가 기준선 17.48%보다 낮다. **IMPROVEMENT_UNCONFIRMED**: PIT 미승인·검증 구간 재사용·최종 홀드아웃 오염 때문에 독립 개선 입증은 아니다.

두 실험은 기존 큐에서 의존성 순서대로 실행됐고 체크포인트 3, 연구 반복 2/5, 외부 API 0건으로 정지했다. 원본 데이터/산출물/연구 코드 해시와 체크포인트를 메모리에 남긴다. 같은 상태에서 재개하면 `ALREADY_EVALUATED`, 메모리가 사라져도 완료 큐를 재검증하고 중복 실행하지 않는다. STOP 파일은 실행을 멈춘다. 고정 템플릿은 Codex가 연구 전용 코드로 작성·검토했으며, 실행 중인 프로그램이 스스로 코드를 패치한 것은 아니다.

첫 커밋 후 제한된 실행 환경에서 `/home/kegor2/agent2_research_state/regime190_agent3_v1_20261101`의 DB 연결이 실패했고 작업 1개가 `FAILED`로 기록됐다. 이를 덮어쓰지 않고 별도 상태 `regime190_agent3_v1b_20261101`에서 같은 읽기 전용 질의를 재실행해 3개 작업을 완료했다. 재개 명령은 후자의 성공 상태를 사용한다.

## 결론과 다음 우선순위

- **VERIFIED:** 기존 연구 결과 재현, 190개 차단 상태 유지, 2개 실험의 큐 실행과 기록, 잠금·해시·재개·중복 방지, 기존 회귀 테스트.
- **INCONCLUSIVE:** 경고·회복의 인과 원인, 후보 국면 전환 규칙의 일반화, 전략 가치.
- **BLOCKED:** 공식 실데이터 백테스트(승인 지표 0), 독립 최종 홀드아웃(기존 기간 열람됨), 실거래 배포.
- **NOT_IMPLEMENTED:** 승인된 LLM 런타임, 열린 범위의 자율 웹 조사, 실행 중 임의 패치 생성/적용, 미래 실패에 대한 일반 목적 자가 수리.
- 다음 단계: (1) 독립적인 행 단위 발표·빈티지·구성 종목·기업행위 근거 확보, (2) 자료 이용권과 과거 캘린더 검증, (3) 실제 미열람 시계열 확보, (4) 고정 가설을 새 독립 기간에서 1회만 평가. 자료가 없으면 최종 결정 `MORE_EVIDENCE_REQUIRED`를 유지한다.

## 재현 명령

```bash
cd /home/kegor2/market-morning-reports-agent3
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -p 'test_*.py'
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -p 'test_*.py'
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m regime190.agent3_controller --state-dir /home/kegor2/agent2_research_state/regime190_agent3_v1b_20261101 --repo /home/kegor2/market-morning-reports-agent3
```

같은 마지막 명령으로 재개한다. 이미 평가한 상태라면 큐를 다시 실행하지 않고 `ALREADY_EVALUATED`를 반환한다. 메모리/소스 해시가 바뀐 경우에는 자동 재실행하지 않고 무결성 오류로 중단한다.

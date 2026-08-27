# 1.6.5.5 Post-Event Result / MI Review

## 목적
주요 일정은 일정 시각이 지나도 캘린더에서 사라지지 않는다. 같은 상세 카드에서 발표 전 판단 질문과 발표 후 실제 결과를 이어서 볼 수 있어야 한다.

## UI 단계
- PRE_EVENT: 판단할 질문 / 왜 중요한가 / 현재 OUR_MI / 확인 지표
- RESULT_PENDING: 일정은 종료됐지만 공식 결과 확인 중
- RESULT_AVAILABLE: 공식 결과 / 예상 대비 차이 / 초기 및 후속 시장반응
- REVIEW_COMPLETE: OUR_MI 사후평가 / 무엇이 바뀌었나 / 다음 추적 항목

## 결과 카드 순서
1. 결과 한줄 요약 — 초보자용
2. 공식 결과 — 수치/결정/문구
3. 예상과 실제 비교
4. 시장 반응 — initial / same_day / next_trading_day / 1w
5. 우리 MI 평가 — SUPPORTED / PARTIAL / CONTRADICTED / INCONCLUSIVE
6. 무엇이 바뀌었나
7. 다음에 볼 것

## 안전장치
- 비공식 보도/YouTube/Telegram만으로 공식 결과 확정 금지
- 시장 가격 반응을 사실 검증 근거로 사용 금지
- 결과 확인 후 기존 prediction 수정 금지
- Prediction Scoreboard와 point-in-time 방식으로 연결
- 완료된 이벤트도 Calendar History에서 유지

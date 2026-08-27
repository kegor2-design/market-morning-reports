# Post-Event Result Card — 1.6.5.5

일정 종료 후 Calendar 상세 카드에 표시할 결과를 작성한다.

원칙:
1. 공식 결과와 시장 반응을 분리한다. 가격 반응은 공식 사실 검증 근거가 아니다.
2. `RESULT_CONFIRMED`, `REACTION_TRACKING`, `REVIEW_COMPLETE`는 반드시 공식 1차 출처 확인 후에만 사용한다.
3. Reuters/YouTube/Telegram 등만 있으면 `PROVISIONAL`로 둔다.
4. 초보자가 첫 문장만 읽어도 "무엇이 결정됐는지" 알 수 있도록 `plain_result_summary`를 쉬운 한국어로 쓴다.
5. `expected_vs_actual`에는 발표 전 시장 예상/OUR_MI와 실제 결과의 차이를 기록한다.
6. 시장 반응은 `initial`, `same_day`, `next_trading_day`, `1w`로 분리하며 관측 가능한 창만 기록한다.
7. `mi_review_status`는 Prediction Scoreboard의 point-in-time 평가와 연결한다. 결과를 본 뒤 과거 예측을 수정하지 않는다.
8. 맞았더라도 원인 설명까지 맞았다고 자동 판정하지 않는다. causal review는 별도 근거로 판단한다.
9. 마지막에는 `what_changed`와 `next_watch`를 써서 이 이벤트 이후 판단이 어떻게 바뀌었고 무엇을 계속 추적할지 설명한다.
10. 일정 종료 후에도 Calendar에서 삭제하지 않고 History/Completed 영역에서 결과를 다시 볼 수 있게 한다.

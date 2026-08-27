# MI Prediction Commit Contract

현재 시점(as_of)에 이용 가능한 정보만 사용해 **검증 가능한 시장 예측 한 건**을 확정한다.

규칙:
- 결론을 사후적으로 바꾸지 않는다.
- `direction`은 UP/DOWN/FLAT 중 하나다.
- `confidence`는 확률처럼 남발하지 말고 현재 증거 강도와 반증 가능성을 반영해 0~1로 준다.
- horizon과 target을 명시한다.
- baseline_value는 as_of 시점 또는 그 직전 공식적으로 사용 가능한 값이어야 한다.
- 예상 범위를 선언할 수 있으면 low/high를 넣는다.
- 어떤 active event, primitive, expert historical claim, source registry가 판단에 사용됐는지 ID로 연결한다.
- 전문가 주장이나 찌라시를 공식 사실로 표현하지 않는다.
- `invalidation_conditions`를 반드시 넣는다.
- 이후 실제 결과가 맞았더라도 causal explanation은 별도 검증한다.
- AI_BASELINE 비교 실행일 경우 OUR_MI_ENGINE 결과를 보지 않은 독립 컨텍스트에서 동일 target/as_of/horizon으로 생성한다.

# MI Prediction Scoreboard 1.6.5.3

## 목적

MI의 품질을 느낌이 아니라 point-in-time 성과로 측정한다. Prediction Scoreboard는 전문가/찌라시의 진위를 판정하는 모듈이 아니라 **우리 MI가 사전에 약속한 방향·기간·confidence가 실제 시장에서 얼마나 유효했는지**를 추적한다.

## 핵심 원칙

1. 예측은 생성 시점에 immutable snapshot으로 동결한다.
2. horizon이 끝나기 전에는 채점하지 않는다.
3. `as_of` 이전 데이터는 평가에 사용하지 않는다.
4. 가격 방향 적중과 causal explanation 검증은 분리한다.
5. HIGH confidence가 실제로 HIGH accuracy인지 calibration을 측정한다.
6. primitive/expert claim/event/source별 성과는 attribution 분석일 뿐 인과 기여도를 자동 확정하지 않는다.
7. 이미 기록된 prediction/evaluation은 같은 ID로 overwrite하지 않는다.

## 저장 구조

- `predictions.jsonl`: 사전 동결된 MI prediction
- `evaluations.jsonl`: maturity 이후 평가 결과
- `scoreboard.json`: 집계 결과

Raw market data는 별도 기존 source/DB를 사용하고 release ZIP에 포함하지 않는다.

## 주요 지표

- Direction accuracy
- Confidence bucket accuracy
- Mean confidence / calibration gap / Brier loss
- Terminal return (%)
- MFE / MAE (%)
- Range hit (예상 범위 선언 시)
- Asset / horizon / regime별 정확도
- Primitive / expert claim / event / source별 attribution 성과

## 해석 주의

`by_expert_claim` 정확도가 높다고 해당 전문가의 설명이 causal truth라는 뜻은 아니다. 마찬가지로 Rumor source가 예측에 자주 포함되어 성과가 높아도 공식 사실 신뢰도로 승격하지 않는다. Expert Corpus validation과 Source Registry verification은 별도 contract를 유지한다.

## 범용 AI와 A/B 비교

`predictor_id`를 사용해 같은 `as_of + target_asset + target_metric + horizon` 예측을 `OUR_MI_ENGINE`, `AI_BASELINE` 등으로 따로 동결할 수 있다. Scoreboard는 동일 comparison key가 maturity 된 경우에만 matched accuracy와 head-to-head win/tie를 집계한다. 이후 정보를 본 AI에게 과거 시점 예측을 다시 시키는 방식은 금지한다.

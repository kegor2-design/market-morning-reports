# MarketMorningPublisher 1.6.5.4 — Beginner-first Calendar Decision Card

## Problem fixed

Existing cards can show a causal label such as `Fed 정책 기대 → 미국 금리/달러 → 원화와 외국인 수급`, but that label does not immediately tell a beginner **what question the engine is trying to answer**.

1.6.5.4 makes the calendar detail card decision-first.

## Public card order

```text
[공식] 9월 FOMC

판단할 질문
Fed가 시장 예상보다 매파적으로 나올까, 완화적으로 나올까?

한줄 설명
금리 숫자만 보지 말고 앞으로 금리를 얼마나 오래 높게 유지할지 확인합니다.

왜 중요한가
Fed의 태도 → 미국 국채금리·달러 → 원/달러 → 외국인 수급 → 국내 증시로 전달될 수 있습니다.

현재 우리 판단
OUR_MI가 존재할 때만 표시. 근거와 confidence를 같이 노출합니다.

무엇을 볼까
- 정책금리: 시장 예상과 실제 결정 차이
- 성명/점도표: 추가 인상 또는 인하 신호 변화
- 미국 2Y/10Y: 발표 직후 금리 방향
- DXY/USD-KRW: 달러와 원화 반응

결과별 시나리오
...

판단이 틀렸다고 볼 조건
...

용어
매파적: 높은 금리를 더 오래 유지하거나 인상을 선호하는 태도
```

## Hard rules

- `decision_question` is the card headline. Causal chains are secondary context.
- `current_view` can only represent OUR_MI. Expert/Rumor content must remain separately labeled.
- Missing current view is allowed. Never manufacture a directional opinion to fill the card.
- Use verified event stage. A cloture/procedural vote is not described as final passage.
- Older records automatically receive conservative fallback explanations so the portal does not show blank cards.

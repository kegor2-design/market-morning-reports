# MMP Calendar Decision Card — Beginner-first contract

For every HIGH/MEDIUM importance calendar event, generate a `decision_card` that answers the question a non-expert actually needs to decide.

## Order shown in UI

1. **판단할 질문** — one plain Korean question. Do not use an unexplained causal-chain label as the headline.
2. **한줄 설명** — what happens at this event and what result matters.
3. **왜 중요한가** — explain the transmission to KR markets in beginner language.
4. **현재 우리 판단** — only when the MI engine has an actual view. If not, say that the engine is waiting for the result; do not invent a stance.
5. **무엇을 볼까** — 2–5 concrete indicators/phrases/prices.
6. **결과별 시나리오** — what would support KR risk-on / risk-off or the relevant asset direction.
7. **판단이 틀렸다고 볼 조건** — explicit invalidation conditions when available.
8. **용어 설명** — only terms that a beginner may not know.

## Style rules

- Prefer `Fed가 예상보다 매파적일까, 완화적일까?` over `Fed 정책 기대 → 미국 금리/달러 → 원화와 외국인 수급`.
- The causal chain belongs under `transmission_path`, not in the headline.
- Explain one financial term in 15–40 Korean characters when needed.
- Separate fact, expert claim, rumor, and OUR_MI. Never present an expert view as the engine's own conclusion.
- Never invent a current view, probability, date, consensus, or market reaction.
- A procedural vote is not a final passage vote. Explain the actual stage.
- Use exact dates/times when verified, and visibly label estimates.

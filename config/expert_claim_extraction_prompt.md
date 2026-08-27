# Historical Expert Claim Extraction Contract

You are extracting reusable historical reasoning from one YouTube transcript for MarketMorningPublisher.

Rules:

1. Do not summarize the whole video. Extract only decision-relevant claims, causal chains, metrics, timing, and invalidation conditions.
2. Separate the primary expert's own view from guest speech, quoted news, broker research, official explanations, and interviewer prompts.
3. `claim_kind` must be one of: `PRIMARY_EXPERT_HYPOTHESIS`, `PRIMARY_EXPERT_RULE`, `PRIMARY_EXPERT_OBSERVATION`, `GUEST_CLAIM`, `QUOTED_REPORT`, `OFFICIAL_EXPLANATION`, `BACKGROUND_ONLY`.
4. Only the first three primary-expert kinds may become reusable expert primitives. Other kinds remain evidence/context.
5. Historical expert speech is never `OFFICIAL_FACT` and must never be promoted merely because market prices later moved in the same direction.
6. Preserve point-in-time meaning. Do not inject facts that became known after the video's publication date.
7. For `TIMESTAMP_VERIFIED` VTT, `source_timestamp_start` and `source_timestamp_end` are mandatory. For `TEXT_VERIFIED` normalized TXT, return empty strings for both fields. Never estimate or invent timestamps.
8. `primitive_key` must be short, stable snake_case describing the reasoning rule rather than the one-off headline. Reuse an existing primitive key when the same reasoning is repeated.
9. `stance` must be `SUPPORT`, `OPPOSE`, or `NEUTRAL` relative to that primitive.
10. `attribution_confidence` must be `HIGH`, `MEDIUM`, or `LOW`. Exclude ambiguous claims rather than pretending HIGH confidence.
11. For Chesley/Park Seik, be especially careful to distinguish Park Seik from other Chesley speakers and quoted articles/reports.
12. For Park Jong-hoon/KPUNCH, distinguish Park's hypothesis from Fed/Treasury/government stated intent or descriptions of mechanics.
13. Output only the schema-compliant JSON object.
14. Encode `expected_direction` as an array of `{asset, direction}` objects; use an empty array when unavailable.
15. Write all claim text, evidence summaries, causal chains, conditions, and other reader-facing prose in Korean. Keep proper nouns as needed.

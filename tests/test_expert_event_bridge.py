import unittest
from market_morning_publisher.expert_historical_corpus import claim_from_llm
from market_morning_publisher.expert_event_bridge import relevant_claims_for_event


class ExpertEventBridgeTest(unittest.TestCase):
    def test_bridge_never_promotes_event_truth(self):
        raw = {
            "speaker":"박종훈", "claim_text":"미국 장기금리와 달러를 함께 봐야 한다", "claim_kind":"PRIMARY_EXPERT_HYPOTHESIS",
            "evidence_summary":"Treasury 수급을 강조", "causal_chain":["국채 공급","장기금리","달러"], "premise_metrics":["US10Y","DXY"],
            "time_horizon":"WEEKS", "related_assets":["USD/KRW"], "related_entities":["Fed","Treasury"], "topics":["달러","장기금리"],
            "expected_direction":{"USD/KRW":"CONDITIONAL"}, "invalidation_conditions":["장기금리 하락"], "primitive_key":"treasury_yield_usd_link",
            "stance":"SUPPORT", "source_timestamp_start":"00:01:00.000", "source_timestamp_end":"00:02:00.000", "attribution_confidence":"HIGH"
        }
        c = claim_from_llm("park_jonghoon_kpunch", "v", "2026-01-01", raw)
        rows = relevant_claims_for_event({"title":"Fed Treasury 장기금리와 원달러", "event_type":"FX_FLOW", "entities":["Fed","Treasury"]}, [c])
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["may_promote_event_truth"])
        self.assertEqual(rows[0]["truth_class"], "EXPERT_HISTORICAL_CLAIM")


if __name__ == "__main__":
    unittest.main()

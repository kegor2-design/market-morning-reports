import unittest

from market_morning_publisher.calendar_event_impact import impact_profile, project_impact_and_scenarios
from market_morning_publisher.event_lifecycle import EventRecord, project_calendar_item
from market_morning_publisher.post_event_result import PostEventResult, compact_result_summary


class CalendarImpactScenarioTest(unittest.TestCase):
    def test_fomc_is_critical_and_has_three_branches(self):
        event = EventRecord(event_id="F1", title="9월 FOMC", event_type="FOMC", truth_class="OFFICIAL_FACT")
        out = project_impact_and_scenarios(event)
        self.assertEqual(out["impact_profile"]["level"], "CRITICAL")
        self.assertGreaterEqual(out["impact_profile"]["score"], 90)
        self.assertEqual({x["scenario_id"] for x in out["outcome_scenarios"]}, {"HAWKISH", "INLINE", "DOVISH"})

    def test_probability_is_not_invented(self):
        event = EventRecord(event_id="F2", title="9월 FOMC", event_type="FOMC")
        scenarios = project_impact_and_scenarios(event)["outcome_scenarios"]
        self.assertTrue(all(x["probability"] is None for x in scenarios))

    def test_only_our_mi_may_supply_probability(self):
        event = EventRecord(
            event_id="F3", title="9월 FOMC", event_type="FOMC",
            decision_card={"scenario_probability_source":"OUR_MI", "scenario_probabilities":{"HAWKISH":0.25,"INLINE":0.5,"DOVISH":0.25}},
        )
        scenarios = {x["scenario_id"]: x for x in project_impact_and_scenarios(event)["outcome_scenarios"]}
        self.assertEqual(scenarios["INLINE"]["probability"], 0.5)
        self.assertEqual(scenarios["INLINE"]["probability_source"], "OUR_MI")

    def test_expert_probability_cannot_be_used(self):
        event = EventRecord(
            event_id="F4", title="9월 FOMC", event_type="FOMC",
            decision_card={"scenario_probability_source":"EXPERT", "scenario_probabilities":{"HAWKISH":0.9}},
        )
        scenarios = project_impact_and_scenarios(event)["outcome_scenarios"]
        self.assertTrue(all(x["probability"] is None for x in scenarios))

    def test_calendar_projection_exposes_badge_and_scenarios(self):
        event = EventRecord(event_id="T1", title="미 재무부 바이백 확대", event_type="TREASURY_BUYBACK")
        card = project_calendar_item(event)["decision_card"]
        self.assertEqual(card["impact_profile"]["level"], "HIGH")
        self.assertTrue(card["impact_profile"]["badge"])
        self.assertGreaterEqual(len(card["outcome_scenarios"]), 3)

    def test_post_event_can_record_realized_scenario(self):
        result = PostEventResult(
            result_state="RESULT_CONFIRMED", verification_class="OFFICIAL_FACT",
            official_result_summary="Fed는 금리를 동결하고 예상보다 매파적인 점도표를 제시했다.",
            official_source_ids=["fed_release"], mi_review_status="PARTIAL",
            matched_scenario_id="HAWKISH", scenario_review_summary="매파 시나리오의 금리·달러 반응이 확인됐다.",
        )
        out = compact_result_summary(result)
        self.assertEqual(out["matched_scenario_id"], "HAWKISH")
        self.assertIn("매파", out["scenario_review_summary"])

    def test_linked_mi_small_boost_does_not_change_meaning(self):
        base = impact_profile(EventRecord(event_id="R1", title="법안 표결", event_type="REGULATION"))
        linked = impact_profile(EventRecord(event_id="R2", title="법안 표결", event_type="REGULATION", linked_mi=["MI-1"]))
        self.assertEqual(linked.score, base.score + 3)
        self.assertEqual(base.level, linked.level)


if __name__ == "__main__":
    unittest.main()

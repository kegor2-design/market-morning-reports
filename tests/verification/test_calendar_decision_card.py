import unittest

from market_morning_publisher.calendar_decision_card import decision_card_from_event
from market_morning_publisher.event_lifecycle import EventRecord, project_calendar_item


class CalendarDecisionCardTest(unittest.TestCase):
    def test_fomc_headline_is_decision_question_not_chain(self):
        event = EventRecord(event_id="E1", title="9월 FOMC", event_type="FOMC", truth_class="OFFICIAL_FACT", status="ACTIVE")
        card = project_calendar_item(event)["decision_card"]
        self.assertIn("Fed", card["decision_question"])
        self.assertTrue(card["decision_question"].endswith("?"))
        self.assertNotIn("→", card["decision_question"])
        self.assertIn("원/달러", card["why_it_matters"])
        self.assertGreaterEqual(len(card["watch_items"]), 3)

    def test_explicit_card_overrides_fallback_but_keeps_missing_help(self):
        event = EventRecord(
            event_id="E2", title="9월 FOMC", event_type="FOMC",
            decision_card={
                "decision_question": "이번 FOMC에서 추가 인상 신호가 나올까?",
                "current_view": "현재 OUR_MI는 동결 가능성을 기본 시나리오로 본다.",
                "current_view_confidence": "MEDIUM",
            },
        )
        card = decision_card_from_event(event)
        self.assertEqual(card.decision_question, "이번 FOMC에서 추가 인상 신호가 나올까?")
        self.assertEqual(card.current_view_confidence, "MEDIUM")
        self.assertTrue(card.why_it_matters)

    def test_no_direction_is_invented_when_engine_has_none(self):
        event = EventRecord(event_id="E3", title="기업 일정", event_type="OTHER")
        card = decision_card_from_event(event)
        self.assertIsNone(card.current_view)

    def test_expected_direction_does_not_become_our_mi_view(self):
        event = EventRecord(event_id="E4", title="미 재무부 장기채 바이백", event_type="TREASURY_BUYBACK", expected_direction={"US10Y":"DOWN_PRESSURE"})
        card = decision_card_from_event(event)
        self.assertIsNone(card.current_view)

    def test_regulation_explains_procedural_stage(self):
        event = EventRecord(event_id="E5", title="CLARITY Act 상원 절차표결", event_type="REGULATION")
        card = decision_card_from_event(event)
        combined = " ".join(x.what_to_check for x in card.watch_items)
        self.assertIn("최종 표결", combined)
        self.assertIn("중간 절차", combined)


if __name__ == "__main__":
    unittest.main()

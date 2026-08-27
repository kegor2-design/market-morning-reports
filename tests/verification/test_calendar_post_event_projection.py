import unittest

from market_morning_publisher.event_lifecycle import EventRecord, merge_candidate, project_calendar_item


class CalendarPostEventProjectionTest(unittest.TestCase):
    def test_projection_switches_to_result_pending_after_event(self):
        event = EventRecord(event_id="E1", title="FOMC", event_type="FOMC", event_date="2026-09-16T18:00:00Z")
        item = project_calendar_item(event, now="2026-09-16T19:00:00Z")
        self.assertEqual(item["calendar_phase"], "RESULT_PENDING")
        self.assertEqual(item["visibility"], "HISTORY")
        self.assertIsNone(item["post_event_result"])

    def test_official_result_projects_on_same_calendar_card(self):
        event = EventRecord(event_id="E2", title="FOMC", event_type="FOMC", event_date="2026-09-16T18:00:00Z")
        event = merge_candidate(event, {
            "title": "FOMC",
            "event_type": "FOMC",
            "post_event_result": {
                "result_state": "RESULT_CONFIRMED",
                "verification_class": "OFFICIAL_FACT",
                "official_result_summary": "Fed는 기준금리를 동결했다.",
                "plain_result_summary": "금리는 그대로였습니다.",
                "official_source_ids": ["official_fed"],
                "expected_vs_actual": "시장 예상과 일치",
                "mi_review_status": "PENDING"
            },
            "evidence": []
        })
        item = project_calendar_item(event, now="2026-09-16T19:00:00Z")
        self.assertEqual(item["calendar_phase"], "RESULT_AVAILABLE")
        self.assertIn("금리는 그대로", item["post_event_result"]["headline"])
        self.assertIn("Fed", item["decision_card"]["decision_question"])


if __name__ == "__main__":
    unittest.main()

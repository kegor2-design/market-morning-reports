import unittest

from market_morning_publisher.post_event_result import (
    PostEventResult,
    calendar_phase,
    compact_result_summary,
    merge_result_payload,
)


class PostEventResultTest(unittest.TestCase):
    def test_event_after_time_without_result_is_pending(self):
        phase = calendar_phase("2026-09-16T18:00:00Z", None, now="2026-09-16T19:00:00Z")
        self.assertEqual(phase, "RESULT_PENDING")

    def test_event_before_time_is_pre_event(self):
        phase = calendar_phase("2026-09-16T18:00:00Z", None, now="2026-09-16T17:00:00Z")
        self.assertEqual(phase, "PRE_EVENT")

    def test_unofficial_report_cannot_be_confirmed(self):
        merged = merge_result_payload(None, {
            "result_state": "RESULT_CONFIRMED",
            "verification_class": "ATTRIBUTABLE_REPORT",
            "plain_result_summary": "보도 결과",
        })
        self.assertEqual(merged["result_state"], "PROVISIONAL")
        self.assertNotEqual(merged["verification_class"], "OFFICIAL_FACT")

    def test_confirmed_result_requires_official_source(self):
        with self.assertRaises(ValueError):
            PostEventResult.from_dict({
                "result_state": "RESULT_CONFIRMED",
                "verification_class": "OFFICIAL_FACT",
                "official_result_summary": "Fed가 금리를 동결했다.",
                "official_source_ids": [],
            })

    def test_confirmed_result_is_beginner_friendly_and_keeps_reactions(self):
        result = PostEventResult.from_dict({
            "result_state": "REACTION_TRACKING",
            "verification_class": "OFFICIAL_FACT",
            "official_result_summary": "Fed는 기준금리를 동결했다.",
            "plain_result_summary": "금리는 그대로였지만 앞으로의 금리 경로가 핵심입니다.",
            "official_source_ids": ["official_fed"],
            "expected_vs_actual": "금리 동결은 예상과 일치",
            "market_reactions": [
                {"window": "initial", "asset": "US2Y", "change_pct": -0.08},
                {"window": "same_day", "asset": "USD/KRW", "change_pct": -0.35}
            ],
        })
        compact = compact_result_summary(result)
        self.assertIn("금리는 그대로", compact["headline"])
        self.assertEqual(len(compact["market_reactions"]), 2)
        self.assertEqual(calendar_phase("2026-09-16T18:00:00Z", result, now="2026-09-16T19:00:00Z"), "RESULT_AVAILABLE")

    def test_official_result_cannot_be_overwritten_by_rumor(self):
        current = {
            "result_state": "RESULT_CONFIRMED",
            "verification_class": "OFFICIAL_FACT",
            "official_result_summary": "공식 결과",
            "official_source_ids": ["official_fed"],
            "mi_review_status": "PENDING",
        }
        merged = merge_result_payload(current, {
            "result_state": "PROVISIONAL",
            "verification_class": "UNVERIFIED",
            "plain_result_summary": "텔레그램 주장",
        })
        self.assertEqual(merged["official_result_summary"], "공식 결과")
        self.assertEqual(merged["verification_class"], "OFFICIAL_FACT")

    def test_review_complete_phase(self):
        result = PostEventResult.from_dict({
            "result_state": "REVIEW_COMPLETE",
            "verification_class": "OFFICIAL_FACT",
            "official_result_summary": "공식 결과",
            "official_source_ids": ["official_source"],
            "mi_review_status": "SUPPORTED",
        })
        self.assertEqual(calendar_phase("2026-09-16T18:00:00Z", result, now="2026-09-20T00:00:00Z"), "REVIEW_COMPLETE")


if __name__ == "__main__":
    unittest.main()

import unittest

from market_morning_publisher.schedule_discovery import extract_schedule_candidates, find_date_mentions, infer_event_type


class ScheduleDiscoveryTest(unittest.TestCase):
    def test_korean_date_range(self):
        rows = find_date_mentions("9월 15~16일 FOMC가 열립니다.", published_at="2026-08-22T00:00:00Z")
        self.assertEqual(rows[0].start_date, "2026-09-15")
        self.assertEqual(rows[0].end_date, "2026-09-16")

    def test_event_types(self):
        self.assertEqual(infer_event_type("9월 16일 FOMC"), "FOMC")
        self.assertEqual(infer_event_type("9월 9일 미 재무부 장기국채 바이백"), "TREASURY_BUYBACK")
        self.assertEqual(infer_event_type("11월 3일 미국 중간선거"), "ELECTION")
        self.assertEqual(infer_event_type("9월 15일 CLARITY Act 상원 표결"), "REGULATION")

    def test_park_jonghoon_fixture_discovers_major_dates(self):
        text = """
8월 28일 잭슨홀 관련 발언을 확인해야 합니다.
9월 9일 미 재무부가 장기국채 바이백 확대를 시작합니다.
9월 15일 CLARITY Act 상원 표결 일정이 있습니다.
9월 15~16일 FOMC가 예정되어 있습니다.
11월 3일 미국 중간선거가 열립니다.
11월 4일 미 재무부 국채 수급 관련 일정도 확인해야 합니다.
"""
        rows = extract_schedule_candidates({
            "source_type": "YOUTUBE_EXPERT",
            "source_id": "cUAwb9CTMHo",
            "source_name": "박종훈의 지식한방",
            "published_at": "2026-08-22T00:00:00Z",
            "text": text,
            "attributable": True,
        })
        dates = {(r["event_date"], r["estimated_end_date"], r["event_type"]) for r in rows}
        self.assertIn(("2026-08-28", None, "JACKSON_HOLE"), dates)
        self.assertIn(("2026-09-09", None, "TREASURY_BUYBACK"), dates)
        self.assertIn(("2026-09-15", None, "REGULATION"), dates)
        self.assertIn(("2026-09-15", "2026-09-16", "FOMC"), dates)
        self.assertIn(("2026-11-03", None, "ELECTION"), dates)
        self.assertGreaterEqual(len(rows), 6)

    def test_expert_candidate_is_not_official(self):
        rows = extract_schedule_candidates({
            "source_type":"YOUTUBE_EXPERT", "source_id":"v1", "published_at":"2026-08-22", "text":"9월 16일 FOMC가 있습니다."
        })
        self.assertFalse(rows[0]["official"])
        self.assertTrue(rows[0]["metadata"]["requires_official_verification"])


if __name__ == "__main__":
    unittest.main()

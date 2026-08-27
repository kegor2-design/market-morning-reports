import unittest

from market_morning_publisher.youtube_chart.time_model import first_bar_after, resolve_actionable_time


class YoutubeChartTimeTest(unittest.TestCase):
    def test_live_claim_uses_stream_start_plus_speech_end(self):
        result = resolve_actionable_time(
            video_published_at=None, livestream_start_at="2026-08-16T23:00:00Z",
            spoken_offset_ms=90_500, is_live=True,
        )
        self.assertEqual(result.publicly_actionable_at, "2026-08-16T23:01:30.500000+00:00")
        self.assertEqual(result.availability_reason, "LIVE_STREAM_START_PLUS_SPEECH_END")

    def test_recorded_claim_uses_publication_not_speech_offset(self):
        result = resolve_actionable_time(
            video_published_at="2026-08-16T23:00:00+00:00", livestream_start_at=None,
            spoken_offset_ms=900_000, is_live=False,
        )
        self.assertEqual(result.publicly_actionable_at, "2026-08-16T23:00:00+00:00")

    def test_date_only_or_naive_timestamp_stays_unknown(self):
        result = resolve_actionable_time(
            video_published_at="20260816", livestream_start_at=None, spoken_offset_ms=1_000, is_live=False,
        )
        self.assertIsNone(result.publicly_actionable_at)
        self.assertEqual(result.availability_precision, "UNKNOWN")

    def test_first_bar_is_strictly_after_actionable_time(self):
        bars = [
            {"timestamp": "2026-08-16T09:00:00Z"},
            {"timestamp": "2026-08-16T10:00:00Z"},
            {"timestamp": "2026-08-16T11:00:00Z"},
        ]
        self.assertEqual(first_bar_after(bars, "2026-08-16T10:00:00Z"), 2)


if __name__ == "__main__":
    unittest.main()


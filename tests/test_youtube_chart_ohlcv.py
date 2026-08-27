import unittest

from market_morning_publisher.youtube_chart.ohlcv import (
    completed_bars_as_of, interval_for_timeframe, parse_yahoo_chart, reconcile_screen_prices,
)


class YoutubeChartOhlcvTest(unittest.TestCase):
    def test_parses_raw_ohlcv_and_preserves_adjusted_close(self):
        payload = {"chart": {"error": None, "result": [{
            "timestamp": [1_700_000_000, 1_700_086_400],
            "indicators": {
                "quote": [{"open": [100, None], "high": [110, None], "low": [95, None], "close": [105, None], "volume": [1000, None]}],
                "adjclose": [{"adjclose": [103, None]}],
            },
        }]}}
        bars = parse_yahoo_chart(payload)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["open"], 100)
        self.assertEqual(bars[0]["adjusted_close"], 103)
        self.assertEqual(bars[0]["price_basis"], "RAW")

    def test_timeframe_is_not_approximated(self):
        self.assertEqual(interval_for_timeframe("DAILY"), "1d")
        self.assertIsNone(interval_for_timeframe("MINUTE_3"))

    def test_reconciles_screen_axis_against_market_range(self):
        bars = [{"low": 98, "high": 102}]
        self.assertEqual(reconcile_screen_prices([{"value": 100}], bars)["status"], "MATCHED")
        self.assertEqual(reconcile_screen_prices([{"value": 500}], bars)["status"], "MISMATCH")

    def test_point_in_time_context_excludes_incomplete_current_bar(self):
        bars = [
            {"timestamp": "2026-08-16T09:00:00Z"},
            {"timestamp": "2026-08-16T10:00:00Z"},
            {"timestamp": "2026-08-16T11:00:00Z"},
        ]
        known = completed_bars_as_of(bars, "2026-08-16T10:30:00Z")
        self.assertEqual([item["timestamp"] for item in known], ["2026-08-16T09:00:00Z"])


if __name__ == "__main__":
    unittest.main()

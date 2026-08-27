import unittest

from market_morning_publisher.youtube_chart.outcomes import evaluate_claim


def bar(hour, opening, high, low, close):
    return {"timestamp": f"2026-08-16T{hour:02d}:00:00+00:00", "open": opening, "high": high, "low": low, "close": close}


class YoutubeChartOutcomesTest(unittest.TestCase):
    def test_long_target_success_and_excursions(self):
        bars = [bar(9, 99, 101, 98, 100), bar(10, 100, 103, 97, 102), bar(11, 102, 111, 101, 109)]
        claim = {"direction": "LONG", "publicly_actionable_at": "2026-08-16T09:30:00Z", "target_price": 110, "invalidation_price": 95}
        result = evaluate_claim(claim, bars, windows=(1, 2), horizon_bars=2)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["entry_price"], 100)
        self.assertEqual(result["mfe_pct"], 11)
        self.assertEqual(result["mae_pct"], -3)

    def test_same_bar_target_and_invalidation_is_ambiguous(self):
        bars = [bar(9, 100, 101, 99, 100), bar(10, 100, 111, 94, 102)]
        claim = {"direction": "LONG", "publicly_actionable_at": "2026-08-16T09:30:00Z", "target_price": 110, "invalidation_price": 95}
        self.assertEqual(evaluate_claim(claim, bars, horizon_bars=1)["status"], "AMBIGUOUS")

    def test_direction_only_claim_is_unscorable_but_keeps_forward_metrics(self):
        bars = [bar(9, 100, 101, 99, 100), bar(10, 100, 105, 96, 103)]
        claim = {"direction": "LONG", "publicly_actionable_at": "2026-08-16T09:30:00Z", "target_price": None, "invalidation_price": None}
        result = evaluate_claim(claim, bars, windows=(1,))
        self.assertEqual(result["status"], "UNSCORABLE")
        self.assertEqual(result["forward_windows"][0]["status"], "COMPLETE")
        self.assertEqual(result["forward_windows"][0]["return_pct"], 3)

    def test_short_mfe_and_mae_are_direction_aware(self):
        bars = [bar(9, 100, 101, 99, 100), bar(10, 100, 105, 90, 95)]
        claim = {"direction": "SHORT", "publicly_actionable_at": "2026-08-16T09:30:00Z", "target_price": None, "invalidation_price": None}
        result = evaluate_claim(claim, bars, windows=(1,))
        self.assertAlmostEqual(result["mfe_pct"], 11.111111, places=5)
        self.assertAlmostEqual(result["mae_pct"], -4.761905, places=5)

    def test_invalid_level_order_is_not_scored(self):
        bars = [bar(9, 100, 101, 99, 100), bar(10, 100, 106, 94, 103)]
        claim = {"direction": "LONG", "publicly_actionable_at": "2026-08-16T09:30:00Z", "target_price": 90, "invalidation_price": 110}
        result = evaluate_claim(claim, bars, horizon_bars=1)
        self.assertEqual(result["status"], "UNSCORABLE")
        self.assertEqual(result["reason"], "INVALID_TARGET_INVALIDATION_ORDER")


if __name__ == "__main__":
    unittest.main()

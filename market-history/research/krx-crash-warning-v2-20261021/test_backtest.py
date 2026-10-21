"""Small behavioral checks for the event boundary and signal timing rules."""
from datetime import date, timedelta
from decimal import Decimal
import unittest

import backtest


class CrashWarningTests(unittest.TestCase):
    def sample(self):
        start = date(2020, 1, 1)
        dates = [(start + timedelta(days=i)).isoformat() for i in range(110)]
        prices = [Decimal("100") for _ in dates]
        prices[60] = Decimal("94")
        prices[65] = Decimal("89")
        prices[75] = Decimal("88")
        return dates, prices

    def test_crash_merges_nearby_threshold_runs_and_records_dates(self):
        dates, prices = self.sample()
        events = backtest.crash_events("KOSPI", dates, prices)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual((event["first5_i"], event["start_i"], event["low_i"], event["recovery_i"]),
                         (60, 65, 75, 76))
        self.assertEqual(event["merged_runs"], 2)

    def test_post_crash_alert_cannot_be_early_hit(self):
        dates, prices = self.sample()
        events = backtest.crash_events("KOSPI", dates, prices)
        late = [{"episode_id": "late", "start_i": 66, "end_i": 66}]
        score, leads, _ = backtest.early_score(dates, events, late, 0, len(dates)-1)
        self.assertEqual(score["hit_events"], 0)
        self.assertEqual(score["tp_episodes"], 0)
        self.assertIsNone(leads[events[0]["event_id"]])

    def test_future_price_change_does_not_change_prior_signals(self):
        _, prices = self.sample()
        before = backtest.signals(prices)
        prices[100] = Decimal("1")
        after = backtest.signals(prices)
        for model in backtest.MODELS:
            self.assertEqual(before[model][:100], after[model][:100], model)


if __name__ == "__main__":
    unittest.main()

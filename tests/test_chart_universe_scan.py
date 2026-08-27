import json
import unittest
from pathlib import Path

from market_morning_publisher.chart_insight.universe import scan_symbol_bars, summarize_universe_events

ROOT=Path(__file__).resolve().parents[1]


class ChartUniverseScanTest(unittest.TestCase):
    def test_scan_uses_only_past_bars_for_primitive_and_future_for_outcome(self):
        registry=json.loads((ROOT/"config/chart_insight_primitives.json").read_text(encoding="utf-8"))
        bars=[]
        for i in range(25):
            px=100+i*0.1
            bars.append({"timestamp":f"2026-01-{i+1:02d}","open":px,"high":px+1,"low":px-1,"close":px,"volume":100})
        # breakout event at index 25 with high relative volume, followed by rising future bars
        bars.append({"timestamp":"2026-01-26","open":110,"high":113,"low":109,"close":112,"volume":300})
        bars.append({"timestamp":"2026-01-27","open":113,"high":115,"low":112,"close":114,"volume":150})
        bars.append({"timestamp":"2026-01-28","open":114,"high":116,"low":113,"close":115,"volume":150})
        rows=scan_symbol_bars("TEST",bars,registry,["BREAKOUT","VOLUME_EXPANSION"],windows=[1,2],minimum_history=20)
        event=[row for row in rows if row["event_timestamp"]=="2026-01-26"][0]
        self.assertEqual(event["future_bars_used_for_features"],0)
        self.assertEqual(event["outcome"]["forward"][0]["bars"],1)
        self.assertGreater(event["outcome"]["forward"][0]["return_pct"],0)

    def test_summary_is_descriptive_not_promotion(self):
        payload=summarize_universe_events([{"symbol":"A","outcome":{"forward":[{"bars":5,"status":"COMPLETE","return_pct":2.0}]}},{"symbol":"B","outcome":{"forward":[{"bars":5,"status":"COMPLETE","return_pct":-1.0}]}}])
        self.assertEqual(payload["forward"]["5"]["positive_rate"],0.5)
        self.assertIn("out-of-sample",payload["warning"])

if __name__ == "__main__": unittest.main()

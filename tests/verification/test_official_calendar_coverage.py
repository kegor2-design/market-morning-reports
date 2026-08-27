import json
import unittest
from pathlib import Path

from market_morning_publisher.official_calendar_coverage import assess_coverage

ROOT = Path(__file__).resolve().parents[2]


class OfficialCalendarCoverageTest(unittest.TestCase):
    def test_seed_contains_park_jonghoon_discovered_core_events_as_official(self):
        raw = json.loads((ROOT / "config/official_calendar_seed_20260827.json").read_text())
        types = {x["event_type"] for x in raw["events"]}
        for required in {"JACKSON_HOLE", "TREASURY_BUYBACK", "FOMC", "ELECTION", "TREASURY_REFUNDING"}:
            self.assertIn(required, types)
        self.assertTrue(all(x["truth_class"] == "OFFICIAL_FACT" for x in raw["events"]))

    def test_required_source_zero_future_events_is_fail(self):
        specs = [{"source_id":"FED_FOMC", "required":True, "freshness_hours":168}]
        out = assess_coverage([], specs, now="2026-08-27T00:00:00Z")
        self.assertEqual(out["overall"], "FAIL")
        self.assertEqual(out["sources"][0]["status"], "FAIL")

    def test_seed_can_produce_nonempty_core_coverage(self):
        seed = json.loads((ROOT / "config/official_calendar_seed_20260827.json").read_text())["events"]
        specs = json.loads((ROOT / "config/official_forward_calendar_sources.json").read_text())["sources"]
        # Seed is bootstrap, so not every annual source is guaranteed to be populated.
        out = assess_coverage(seed, specs, now="2026-08-27T00:00:00Z")
        by_id = {x["source_id"]: x for x in out["sources"]}
        self.assertGreater(by_id["FED_FOMC"]["future_events"], 0)
        self.assertGreater(by_id["BLS_RELEASES"]["future_events"], 0)
        self.assertGreater(by_id["BEA_RELEASES"]["future_events"], 0)
        self.assertGreater(by_id["UST_REFUNDING"]["future_events"], 0)


if __name__ == "__main__":
    unittest.main()

import unittest
from market_morning_publisher.event_lifecycle import EventRecord
from market_morning_publisher.source_performance import build_source_performance


class SourcePerformanceTest(unittest.TestCase):
    def test_empty_accuracy_until_decided(self):
        ev = EventRecord(event_id="e", title="x", event_type="OTHER", status="UNVERIFIED", truth_class="UNVERIFIED", evidence=[{
            "source_type":"TELEGRAM", "source_id":"1", "claim":"x", "stance":"SUPPORT",
            "metadata":{"source_registry_id":"tg_x"}
        }])
        row = build_source_performance([ev])[0]
        self.assertIsNone(row["verification_hit_rate"])
        self.assertEqual(row["open"], 1)

    def test_confirmed_and_denied_are_counted(self):
        confirmed = EventRecord(event_id="a", title="x", event_type="OTHER", status="ACTIVE", truth_class="OFFICIAL_FACT", evidence=[{
            "source_type":"TELEGRAM", "source_id":"1", "claim":"x", "stance":"SUPPORT", "metadata":{"source_registry_id":"tg_x"}
        }])
        denied = EventRecord(event_id="b", title="y", event_type="OTHER", status="REJECTED", truth_class="OFFICIAL_FACT", evidence=[{
            "source_type":"TELEGRAM", "source_id":"2", "claim":"y", "stance":"SUPPORT", "metadata":{"source_registry_id":"tg_x"}
        }])
        row = build_source_performance([confirmed, denied])[0]
        self.assertEqual(row["confirmed"], 1)
        self.assertEqual(row["denied"], 1)
        self.assertEqual(row["verification_hit_rate"], 0.5)

if __name__ == "__main__": unittest.main()

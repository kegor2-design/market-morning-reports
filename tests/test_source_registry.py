import json
import tempfile
import unittest
from pathlib import Path

from market_morning_publisher.source_registry import load_source_registry


class SourceRegistryTest(unittest.TestCase):
    def test_registry_has_expected_shape(self):
        reg = load_source_registry("config/source_registry.json")
        self.assertEqual(len(reg.entries), 29)
        self.assertTrue({"official_us_treasury", "official_kansas_city_fed", "official_us_congress", "official_fec"} <= {x.id for x in reg.entries})
        self.assertEqual(sum(1 for x in reg.entries if x.platform == "TELEGRAM"), 18)

    def test_stockinfo_network_is_not_corroboration_eligible(self):
        reg = load_source_registry("config/source_registry.json")
        row = reg.enrich({"source_type":"TELEGRAM", "channel":"@stockinfojji", "message_id":"1", "text":"x"})
        self.assertEqual(row["metadata"]["independence_group"], "stockinfo7_network")
        self.assertFalse(row["metadata"]["corroboration_eligible"])
        self.assertFalse(row["attributable"])

    def test_research_channel_is_attributable_not_official(self):
        reg = load_source_registry("config/source_registry.json")
        row = reg.enrich({"source_type":"TELEGRAM", "channel":"@sksresearch", "message_id":"1", "text":"x"})
        self.assertEqual(row["source_type"], "TELEGRAM_NAMED")
        self.assertTrue(row["attributable"])
        self.assertFalse(row["metadata"]["official_capability"])


if __name__ == "__main__":
    unittest.main()

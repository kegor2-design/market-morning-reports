import unittest

from market_morning_publisher.publication_views import (
    build_closing_review_view,
    build_morning_report_view,
    build_premarket_mi_view,
)


class PublicationViewsTest(unittest.TestCase):
    def test_report_does_not_regenerate_mi(self):
        out = build_morning_report_view({"as_of": "2026-08-27", "major_news": [{"id": 1}]})
        self.assertEqual(out["guardrail"], "REPORT_VIEW_DOES_NOT_REGENERATE_MI")

    def test_premarket_requires_frozen_identity(self):
        with self.assertRaises(ValueError):
            build_premarket_mi_view({"as_of": "2026-08-27"})

    def test_premarket_preserves_snapshot(self):
        scenario = {"scenario_id": "MI-S-1", "as_of": "2026-08-27T08:20:00+09:00", "base_scenario": {"confidence": 0.68}}
        out = build_premarket_mi_view(scenario, short_term_map={"overall_state": "RISK_ON"})
        self.assertEqual(out["base_scenario"]["confidence"], 0.68)
        self.assertEqual(out["publication_guardrail"], "FROZEN_SCENARIO_ONLY")

    def test_closing_uses_original_prediction(self):
        out = build_closing_review_view({"prediction_id": "P-1", "direction": "UP"}, {"status": "PARTIAL"})
        self.assertEqual(out["original_prediction"]["direction"], "UP")
        self.assertEqual(out["publication_guardrail"], "ORIGINAL_PREDICTION_IMMUTABLE")


if __name__ == "__main__":
    unittest.main()

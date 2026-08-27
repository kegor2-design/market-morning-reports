import json
import unittest
from pathlib import Path

from market_morning_publisher.insight_engine.causal_flow import build_causal_flow_packet
from market_morning_publisher.insight_engine.reasoning import build_reasoning_packet


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/global_causal_flows.json").read_text(encoding="utf-8"))


class GlobalCausalFlowTest(unittest.TestCase):
    def test_unrelated_event_does_not_force_a_template(self):
        packet = build_causal_flow_packet({"headline": "기업 분기 실적"}, config=CONFIG)
        self.assertEqual(packet["status"], "NO_TEMPLATE")
        self.assertEqual(packet["paths"], [])

    def test_japan_event_stays_needs_data_without_evidence(self):
        packet = build_causal_flow_packet({"headline": "BOJ 금리 인상"}, config=CONFIG)
        self.assertEqual(packet["status"], "NEEDS_DATA")
        self.assertIn("jgb_10y", packet["missing_metrics"])
        self.assertTrue(all(path["status"] == "NEEDS_DATA" for path in packet["paths"]))

    def test_japan_duration_path_activates_only_when_gates_match(self):
        observations = {
            "jgb_10y": {"state": "RISING"},
            "japan_foreign_bond_flow": {"state": "REPATRIATING"},
            "term_premium_10y": {"state": "RISING"},
        }
        packet = build_causal_flow_packet(
            {"headline": "일본은행 정책 정상화", "tags": ["JGB"]},
            config=CONFIG,
            observations=observations,
        )
        duration = next(path for path in packet["paths"] if path["path_id"] == "JP_TO_US_DURATION_REALLOCATION")
        self.assertEqual(duration["status"], "ACTIVE")
        self.assertEqual(packet["status"], "ACTIVE")
        self.assertTrue(duration["invalidation_conditions"])

    def test_contradicting_required_metric_marks_path_inactive(self):
        observations = {
            "jgb_10y": {"state": "FALLING"},
            "japan_foreign_bond_flow": {"state": "REPATRIATING"},
            "us_10y": {"state": "RISING"},
        }
        packet = build_causal_flow_packet({"headline": "BOJ 회의"}, config=CONFIG, observations=observations)
        duration = next(path for path in packet["paths"] if path["path_id"] == "JP_TO_US_DURATION_REALLOCATION")
        self.assertEqual(duration["status"], "INACTIVE")
        self.assertIn("jgb_10y", duration["evidence"]["contradicting_metrics"])

    def test_reasoning_packet_contains_causal_flow(self):
        packet = build_reasoning_packet(
            {"headline": "BOJ 금리 인상"},
            metric_registry={"metrics": []},
            playbook_config={"playbooks": [], "standard_reasoning_steps": []},
            historical_cases=[],
            causal_flow_config=CONFIG,
        )
        self.assertIn("global_causal_flow", packet)
        self.assertEqual(packet["global_causal_flow"]["selected_templates"], ["JAPAN_RATE_NORMALIZATION"])


if __name__ == "__main__":
    unittest.main()

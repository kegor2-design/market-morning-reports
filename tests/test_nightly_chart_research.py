import json
import unittest
from pathlib import Path

from market_morning_publisher.chart_insight.research import build_nightly_chart_research, build_strategy_candidates

ROOT = Path(__file__).resolve().parents[1]


class NightlyChartResearchTest(unittest.TestCase):
    def setUp(self):
        self.primitives=json.loads((ROOT/"config/chart_insight_primitives.json").read_text(encoding="utf-8"))
        self.policy=json.loads((ROOT/"config/nightly_chart_research.json").read_text(encoding="utf-8"))

    def test_chart_strategy_becomes_discovered_not_accepted_rule(self):
        claims=[{
            "claim_id":"c1","channel_id":"x","channel_name":"X","classification":"ACTION_RULE","importance":"HIGH",
            "chart_analysis_requested":True,"claim_summary_ko":"저항을 돌파하고 거래량이 증가하면 확인한다",
            "causal_chain":[],"invalidation_conditions":["저항 아래 재진입"],"chart_evidence":{"status":"PENDING","records":[]},
            "chart_strategy":{"is_strategy_candidate":True,"method_family":"BREAKOUT_VOLUME","primitive_candidates":["BREAKOUT","VOLUME_EXPANSION"],
                "entry_conditions":["저항 돌파"],"confirmation_conditions":["거래량 증가"],"exit_conditions":[],"invalidation_conditions":["저항 아래 재진입"],
                "risk_management":[],"timeframe_hint":"DAILY","asset_hint":"UNKNOWN","explicit_numeric_rules":[],"reasoning":[],"failure_pattern":["돌파 후 재진입"],"new_method_terms":[],"existing_rule_challenge":""}
        }]
        rows=build_strategy_candidates(claims,[{"id":"x","role":"CHART"}],self.primitives)
        self.assertEqual(rows[0]["lifecycle_status"],"DISCOVERED")
        self.assertFalse(rows[0]["independently_verified_edge"])
        self.assertIn("NEW_FAILURE_RULE",rows[0]["candidate_types"])

    def test_point_in_time_supported_source_example_only_reaches_research_candidate(self):
        claims=[{
            "claim_id":"c1","channel_id":"x","classification":"ACTION_RULE","importance":"HIGH","chart_analysis_requested":True,
            "claim_summary_ko":"신고가 돌파","causal_chain":[],"invalidation_conditions":[],
            "chart_evidence":{"status":"PARTIAL","records":[{"source_claim_id":"c1","primitive_mapping_status":"SUPPORTED_BY_POINT_IN_TIME_CHART"}]},
            "chart_strategy":{"is_strategy_candidate":True,"method_family":"BREAKOUT","primitive_candidates":["BREAKOUT"],"entry_conditions":[],"confirmation_conditions":[],"exit_conditions":[],"invalidation_conditions":[],"risk_management":[],"timeframe_hint":"DAILY","asset_hint":"UNKNOWN","explicit_numeric_rules":[],"reasoning":[],"failure_pattern":[],"new_method_terms":[],"existing_rule_challenge":""}
        }]
        rows=build_strategy_candidates(claims,[{"id":"x"}],self.primitives)
        self.assertEqual(rows[0]["lifecycle_status"],"RESEARCH_CANDIDATE")
        self.assertNotIn(rows[0]["lifecycle_status"],{"HISTORICALLY_SUPPORTED","OUT_OF_SAMPLE_SUPPORTED","OUR_CHART_PRINCIPLE"})

    def test_historical_queue_refuses_unverified_live_adapter(self):
        payload=build_nightly_chart_research("2026-08-24",[{
            "claim_id":"c1","channel_id":"x","classification":"ACTION_RULE","importance":"HIGH","chart_analysis_requested":True,
            "claim_summary_ko":"돌파","causal_chain":[],"invalidation_conditions":[],"chart_evidence":{"records":[]},
            "chart_strategy":{"is_strategy_candidate":True,"method_family":"BREAKOUT","primitive_candidates":["BREAKOUT"],"entry_conditions":[],"confirmation_conditions":[],"exit_conditions":[],"invalidation_conditions":[],"risk_management":[],"timeframe_hint":"DAILY","asset_hint":"UNKNOWN","explicit_numeric_rules":[],"reasoning":[],"failure_pattern":[],"new_method_terms":[],"existing_rule_challenge":""}
        }],[{"id":"x"}],self.primitives,self.policy)
        self.assertEqual(payload["historical_research_queue"][0]["status"],"WAITING_FOR_LIVE_DATA_ADAPTER")
        self.assertTrue(payload["historical_research_queue"][0]["point_in_time_required"])

    def test_release_adds_broad_research_only_chart_sources(self):
        cfg=json.loads((ROOT/"config/youtube_insight_channels.json").read_text(encoding="utf-8"))
        by={row["id"]:row for row in cfg["channels"]}
        for cid in ("smb_capital","traderlion","rayner_teo"):
            self.assertTrue(by[cid]["enabled"])
            self.assertTrue(by[cid]["research_only"])
            self.assertTrue(by[cid]["chart_research_only"])
            self.assertNotEqual(by[cid]["source_weight"],"HIGH")

    def test_data_contract_requires_survivor_and_point_in_time_controls(self):
        contract=json.loads((ROOT/"config/chart_research_data_contract.json").read_text(encoding="utf-8"))
        text=" ".join(contract["requirements"]).casefold()
        self.assertIn("survivor bias",text)
        self.assertIn("completed",text)
        self.assertEqual(contract["live_adapter_status"],"PENDING_CODEX_SERVER_SCHEMA_CHECK")

if __name__ == "__main__": unittest.main()

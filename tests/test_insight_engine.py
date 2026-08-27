import json
import tempfile
import unittest
from pathlib import Path

from market_morning_publisher.insight_engine.history import build_case_market_snapshot, find_analog_cases
from market_morning_publisher.insight_engine.hypothesis import assess_hypothesis, source_performance, upsert_hypothesis
from market_morning_publisher.insight_engine.reasoning import build_engine_update_candidates, build_reasoning_packet
from market_morning_publisher.insight_engine.registry import collection_plan, load_metric_registry, registry_coverage, validate_metric_registry
from market_morning_publisher.insight_engine.states import build_market_states
from market_morning_publisher.insight_engine.vintage import latest_value_as_of, upsert_vintage


class InsightEngineTest(unittest.TestCase):
    def test_release_metric_registry_is_valid_and_contains_seik_and_jonghoon_metrics(self):
        root = Path(__file__).resolve().parents[1]
        registry = load_metric_registry(root / "config/insight_metric_registry.json")
        mids = {row["metric_id"] for row in registry["metrics"]}
        for metric_id in (
            "term_premium_10y", "fima_usage", "treasury_auction_quality",
            "forward_eps_kospi_12m", "foreign_kospi200_futures_net",
            "forced_liquidation_kr", "semiconductor_export_10day",
        ):
            self.assertIn(metric_id, mids)

    def test_registry_requires_reason_for_accepted_metric(self):
        with self.assertRaises(ValueError):
            validate_metric_registry({"metrics": [{"metric_id": "x", "decision": "ACCEPT_P0"}]})

    def test_registry_coverage_preserves_unknown(self):
        payload = {"metrics": [
            {"metric_id": "a", "decision": "ACCEPT_P0", "why_collect": "x", "point_in_time_required": False},
            {"metric_id": "b", "decision": "ACCEPT_P1", "why_collect": "x", "point_in_time_required": False},
        ]}
        cov = registry_coverage(payload, {"a": {"state": "RISING", "value": 1}, "b": {"state": "UNKNOWN"}})
        self.assertEqual(cov["observed"], 1)
        self.assertEqual(cov["unknown_metric_ids"], ["b"])

    def test_point_in_time_vintage_uses_only_values_released_by_cutoff(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "vintages.jsonl"
            upsert_vintage(path, {"metric_id": "gdp", "observation_date": "2026-06-30", "released_at": "2026-07-30T12:30:00+00:00", "value": 1.0, "source": "BEA"})
            upsert_vintage(path, {"metric_id": "gdp", "observation_date": "2026-06-30", "released_at": "2026-08-27T12:30:00+00:00", "value": 1.4, "source": "BEA"})
            first = latest_value_as_of(path, "gdp", "2026-08-01T00:00:00+00:00")
            later = latest_value_as_of(path, "gdp", "2026-09-01T00:00:00+00:00")
            self.assertEqual(first["value"], 1.0)
            self.assertEqual(later["value"], 1.4)

    def test_historical_analog_uses_tags_not_title_only(self):
        cases = [
            {"case_id": "a", "start_date": "2019-01-01", "tags": ["TREASURY", "LIQUIDITY"]},
            {"case_id": "b", "start_date": "2020-01-01", "tags": ["PANDEMIC"]},
        ]
        out = find_analog_cases(cases, ["TREASURY", "BUYBACK"])
        self.assertEqual(out[0]["case_id"], "a")
        self.assertGreater(out[0]["similarity_score"], 0)

    def test_historical_snapshot_records_actual_observation_dates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "data.csv"
            data.write_text("date,x\n2020-01-01,100\n2020-02-01,110\n2020-03-01,90\n", encoding="utf-8")
            case = {"case_id": "x", "title_ko": "x", "start_date": "2020-01-15", "series": [{"id": "x", "path": "data.csv", "column": "x"}]}
            out = build_case_market_snapshot(root, case, windows=[5, 20])
            self.assertEqual(out["series"]["x"]["baseline_date"], "2020-01-01")
            self.assertEqual(out["series"]["x"]["points"]["D+20"]["observed_date"], "2020-02-01")

    def test_hypothesis_ledger_preserves_assessment_history(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "hyp.jsonl"
            row = upsert_hypothesis(path, {"source_lens": "PARK_JONG_HOON", "hypothesis": "x", "status": "OPEN"})
            updated = assess_hypothesis(path, row["hypothesis_id"], status="PARTIAL", evidence=["a"], note="first check")
            self.assertEqual(updated["status"], "PARTIAL")
            self.assertEqual(len(updated["assessments"]), 1)
            perf = source_performance([updated])
            self.assertEqual(perf["PARK_JONG_HOON"]["closed"], 1)
            self.assertEqual(perf["PARK_JONG_HOON"]["calibration_status"], "INSUFFICIENT_SAMPLE")

    def test_market_states_do_not_invent_missing_forward_eps(self):
        out = build_market_states({"breadth_advance_pct_kr": {"value": 60, "state": "OBSERVED"}, "breadth_above_60dma_kr": {"value": 60, "state": "OBSERVED"}})
        self.assertEqual(out["EARNINGS_STATE"]["state"], "UNKNOWN")
        self.assertEqual(out["MARKET_BREADTH_STATE"]["state"], "HEALTHY")

    def test_earnings_state_requires_forward_eps_and_revision_breadth(self):
        observations = {
            "forward_eps_kospi_12m": {"state": "RISING", "value": 300, "changes": {"20p": 5}},
            "earnings_revision_breadth_kospi": {"state": "OBSERVED", "value": 12},
        }
        out = build_market_states(observations)
        self.assertEqual(out["EARNINGS_STATE"]["state"], "IMPROVING")

    def test_reasoning_packet_selects_treasury_and_history_and_missing_data(self):
        registry = {"metrics": [
            {"metric_id": "us_30y", "decision": "ACCEPT_P0", "why_collect": "x", "point_in_time_required": False},
            {"metric_id": "term_premium_10y", "decision": "ACCEPT_P0", "why_collect": "x", "point_in_time_required": False},
        ]}
        playbooks = {"standard_reasoning_steps": [{"step": 1, "id": "EVENT", "question": "what"}], "playbooks": [
            {"id": "GENERAL_EVENT_REASONING", "triggers": [], "tags": ["GENERAL"], "questions": [], "required_metrics": []},
            {"id": "TREASURY_FUNDING", "triggers": ["BUYBACK"], "tags": ["TREASURY"], "questions": ["who buys"], "required_metrics": ["us_30y", "term_premium_10y"]},
        ]}
        cases = [{"case_id": "hist", "start_date": "2024-01-01", "tags": ["TREASURY"]}]
        out = build_reasoning_packet({"type": "TREASURY_BUYBACK", "headline": "buyback expanded", "tags": ["TREASURY"]}, metric_registry=registry, playbook_config=playbooks, historical_cases=cases, observations={"us_30y": {"state": "RISING", "value": 5.0}}, hypotheses=[])
        self.assertIn("TREASURY_FUNDING", out["selected_playbooks"])
        self.assertIn("term_premium_10y", out["missing_metrics"])
        self.assertEqual(out["historical_analogs"][0]["case_id"], "hist")
        self.assertIn("NEEDS_DATA", out["status"])

    def test_youtube_claim_can_propose_engine_update_but_not_auto_accept(self):
        registry = {"metrics": [{"metric_id": "known", "decision": "ACCEPT_P0", "why_collect": "x", "point_in_time_required": False}]}
        playbooks = {"playbooks": [{"id": "KNOWN"}]}
        claims = [{"claim_id": "c1", "channel_id": "kpunch", "claim_summary_ko": "새 지표", "metric_ids": ["new_metric"], "data_needed": ["MMF 월간 배분"], "playbook_ids": ["NEW_PLAYBOOK"]}]
        out = build_engine_update_candidates(claims, registry, playbooks)
        keys = {(row["candidate_type"], row["key"]) for row in out}
        self.assertIn(("METRIC", "new_metric"), keys)
        self.assertIn(("DATA_NEED", "MMF 월간 배분"), keys)
        self.assertIn(("PLAYBOOK", "NEW_PLAYBOOK"), keys)
        self.assertTrue(all(row["decision"] == "REVIEW_REQUIRED" for row in out))

    def test_release_historical_cases_include_repo_taper_and_2026_buyback(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads((root / "config/historical_cases.json").read_text(encoding="utf-8"))
        ids = {row["case_id"] for row in payload["cases"]}
        self.assertIn("HIST-2019-REPO", ids)
        self.assertIn("HIST-2013-TAPER-TANTRUM", ids)
        self.assertIn("HIST-2026-BUYBACK-MIDTERM", ids)
        self.assertIn("Point-in-Time", payload["point_in_time_rule"])

    def test_release_source_lenses_keep_expert_weight_provisional(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads((root / "config/source_lenses.json").read_text(encoding="utf-8"))
        by_id = {row["id"]: row for row in payload["lenses"]}
        self.assertEqual(by_id["PARK_JONG_HOON"]["provisional_weight"], "HIGH_PROVISIONAL")
        self.assertEqual(by_id["PARK_SE_IK"]["provisional_weight"], "HIGH")
        self.assertIn("never automatic facts", payload["policy"])

    def test_collection_plan_separates_active_and_pending_p0(self):
        payload = {"metrics": [
            {"metric_id": "a", "decision": "ACCEPT_P0", "why_collect": "x", "point_in_time_required": False, "adapter_status": "ACTIVE"},
            {"metric_id": "b", "decision": "ACCEPT_P0", "why_collect": "x", "point_in_time_required": False, "adapter_status": "PENDING"},
        ]}
        out = collection_plan(payload)
        self.assertEqual([row["metric_id"] for row in out["ACTIVE_P0"]], ["a"])
        self.assertEqual([row["metric_id"] for row in out["PENDING_P0"]], ["b"])

    def test_release_reasoning_playbook_has_twenty_standard_steps_and_expert_evidence(self):
        root = Path(__file__).resolve().parents[1]
        playbooks = json.loads((root / "config/insight_reasoning_playbooks.json").read_text(encoding="utf-8"))
        self.assertEqual(len(playbooks["standard_reasoning_steps"]), 20)
        evidence = json.loads((root / "config/expert_method_evidence.json").read_text(encoding="utf-8"))
        self.assertIn("PARK_JONG_HOON", evidence["sources"])
        self.assertIn("PARK_SE_IK", evidence["sources"])
        self.assertTrue(any(row["theme"] == "Earnings revisions" for row in evidence["sources"]["PARK_SE_IK"]["themes"]))

    def test_reasoning_packet_keeps_chart_and_nightly_as_evidence_layers(self):
        registry = {"metrics": []}
        playbooks = {"standard_reasoning_steps": [], "playbooks": [{"id": "GENERAL_EVENT_REASONING", "triggers": [], "required_metrics": [], "questions": []}]}
        out = build_reasoning_packet(
            {"type": "GENERAL", "headline": "test", "tags": []},
            metric_registry=registry, playbook_config=playbooks, historical_cases=[], observations={}, hypotheses=[],
            chart_insight={"status": "SHADOW_READY", "signal": "BREAKOUT"},
            nightly_youtube={"disagreement_issue_count": 1},
        )
        self.assertEqual(out["chart_insight_evidence"]["signal"], "BREAKOUT")
        self.assertEqual(out["nightly_youtube_evidence"]["disagreement_issue_count"], 1)
        self.assertTrue(any("independent evidence layer" in rule for rule in out["guardrails"]))


if __name__ == "__main__":
    unittest.main()

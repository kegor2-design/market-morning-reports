from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from market_morning_publisher.mi_prediction_scoreboard import (
    Observation,
    PredictionRecord,
    append_jsonl_once,
    build_scoreboard,
    evaluate_prediction,
)
from market_morning_publisher.mi_prediction_bridge import capture_explicit_predictions, prediction_from_mi_snapshot


class PredictionScoreboardTest(unittest.TestCase):
    def pred(self, **kwargs):
        base = dict(
            mi_id="MI-301",
            as_of="2026-08-01T00:00:00Z",
            target_asset="USDKRW",
            target_metric="close",
            horizon="1D",
            direction="DOWN",
            confidence=0.80,
            baseline_value=1400.0,
            primitive_keys=["fx_flow"],
            expert_claim_ids=["claim-1"],
            event_ids=["event-1"],
            source_registry_ids=["src-1"],
        )
        base.update(kwargs)
        return PredictionRecord.create(**base)

    def test_future_prediction_is_not_scored_early(self):
        p = self.pred()
        e = evaluate_prediction(p, [Observation("2026-08-01T12:00:00Z", 1390)], evaluated_at="2026-08-01T12:00:00Z")
        self.assertEqual(e.state, "PENDING")
        self.assertIsNone(e.direction_correct)

    def test_point_in_time_ignores_pre_prediction_observation(self):
        p = self.pred()
        e = evaluate_prediction(p, [
            Observation("2026-07-31T23:00:00Z", 1200),
            Observation("2026-08-02T00:00:00Z", 1380),
        ], evaluated_at="2026-08-02T00:00:00Z")
        self.assertEqual(e.state, "SCORED")
        self.assertTrue(e.direction_correct)
        self.assertAlmostEqual(e.terminal_return_pct, (1380/1400-1)*100)

    def test_first_observation_at_or_after_maturity_is_terminal(self):
        p = self.pred()
        e = evaluate_prediction(p, [
            Observation("2026-08-01T12:00:00Z", 1410),
            Observation("2026-08-02T01:00:00Z", 1386),
            Observation("2026-08-03T00:00:00Z", 1300),
        ], evaluated_at="2026-08-03T00:00:00Z")
        self.assertEqual(e.terminal_value, 1386)
        self.assertGreater(e.mfe_pct, 0)
        self.assertLess(e.mae_pct, 0)

    def test_flat_band(self):
        p = self.pred(direction="FLAT", flat_band_pct=0.5)
        e = evaluate_prediction(p, [Observation("2026-08-02T00:00:00Z", 1405)], evaluated_at="2026-08-02T00:00:00Z")
        self.assertEqual(e.actual_direction, "FLAT")
        self.assertTrue(e.direction_correct)

    def test_expected_range_hit(self):
        p = self.pred(expected_range_low=1370, expected_range_high=1390)
        e = evaluate_prediction(p, [Observation("2026-08-02T00:00:00Z", 1380)], evaluated_at="2026-08-02T00:00:00Z")
        self.assertTrue(e.range_hit)

    def test_context_snapshot_is_stable_and_nonempty(self):
        p = prediction_from_mi_snapshot(
            {"mi_id": "MI-1", "summary": "환율 하락", "invalidation_conditions": ["DXY 급등"]},
            as_of="2026-08-01T00:00:00Z", target_asset="USDKRW", target_metric="close",
            horizon="1D", direction="DOWN", confidence=0.8, baseline_value=1400,
        )
        self.assertEqual(len(p.context_snapshot_sha256), 64)
        self.assertIn("DXY 급등", p.invalidation_conditions)

    def test_scoreboard_confidence_calibration(self):
        p1 = self.pred(mi_id="MI-1", confidence=0.80)
        p2 = self.pred(mi_id="MI-2", confidence=0.55, direction="UP")
        e1 = evaluate_prediction(p1, [Observation("2026-08-02T00:00:00Z", 1380)], evaluated_at="2026-08-02T00:00:00Z")
        e2 = evaluate_prediction(p2, [Observation("2026-08-02T00:00:00Z", 1380)], evaluated_at="2026-08-02T00:00:00Z")
        board = build_scoreboard([p1,p2],[e1,e2])
        self.assertEqual(board["overall"]["count"], 2)
        self.assertAlmostEqual(board["overall"]["accuracy"], 0.5)
        self.assertEqual(board["by_confidence"]["HIGH"]["accuracy"], 1.0)
        self.assertEqual(board["by_confidence"]["LOW"]["accuracy"], 0.0)
        self.assertIsNotNone(board["overall"]["mean_brier_loss"])

    def test_attribution_dimensions_exist(self):
        p = self.pred()
        e = evaluate_prediction(p, [Observation("2026-08-02T00:00:00Z", 1380)], evaluated_at="2026-08-02T00:00:00Z")
        board = build_scoreboard([p],[e])
        self.assertIn("fx_flow", board["by_primitive"])
        self.assertIn("claim-1", board["by_expert_claim"])
        self.assertIn("event-1", board["by_event"])
        self.assertIn("src-1", board["by_source"])

    def test_causal_validation_is_separate(self):
        p = self.pred()
        e = evaluate_prediction(p, [Observation("2026-08-02T00:00:00Z", 1380)], evaluated_at="2026-08-02T00:00:00Z")
        self.assertEqual(e.causal_validation_status, "SEPARATE_NOT_SCORED_HERE")

    def test_append_is_idempotent(self):
        p = self.pred()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"pred.jsonl"
            self.assertTrue(append_jsonl_once(path, p.to_dict(), id_field="prediction_id"))
            self.assertFalse(append_jsonl_once(path, p.to_dict(), id_field="prediction_id"))
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)

    def test_matched_ai_baseline_comparison(self):
        ours = self.pred(mi_id="MI-OUR", predictor_id="OUR_MI_ENGINE", direction="DOWN", confidence=0.8)
        ai = self.pred(mi_id="AI-B1", predictor_id="AI_BASELINE", direction="UP", confidence=0.7)
        obs = [Observation("2026-08-02T00:00:00Z", 1380)]
        ours_e = evaluate_prediction(ours, obs, evaluated_at="2026-08-02T00:00:00Z")
        ai_e = evaluate_prediction(ai, obs, evaluated_at="2026-08-02T00:00:00Z")
        board = build_scoreboard([ours, ai], [ours_e, ai_e])
        self.assertEqual(board["matched_comparison_groups"], 1)
        self.assertEqual(board["matched_by_predictor"]["OUR_MI_ENGINE"]["accuracy"], 1.0)
        self.assertEqual(board["matched_by_predictor"]["AI_BASELINE"]["accuracy"], 0.0)
        key = "AI_BASELINE__vs__OUR_MI_ENGINE"
        self.assertEqual(board["head_to_head"][key]["b_wins"], 1)

    def test_morning_bridge_commits_only_explicit_predictions(self):
        analysis = {"mi_predictions": [{
            "mi_id": "MI-MORNING-1", "target_asset": "USDKRW", "target_metric": "close",
            "horizon": "1D", "direction": "DOWN", "confidence": 0.8, "baseline_value": 1400,
            "summary": "원화 강세 가설", "invalidation_conditions": ["1410 상회"],
        }, {"mi_id": "NARRATIVE_ONLY", "summary": "방향 없는 서술"}]}
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "predictions.jsonl"
            first = capture_explicit_predictions(analysis, as_of="2026-08-01T00:00:00Z", ledger=ledger)
            second = capture_explicit_predictions(analysis, as_of="2026-08-01T00:00:00Z", ledger=ledger)
            self.assertEqual(first, {"created": 1, "skipped": 1})
            self.assertEqual(second, {"created": 0, "skipped": 2})


if __name__ == "__main__":
    unittest.main()

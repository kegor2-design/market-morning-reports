import unittest
from datetime import datetime, timezone
from pathlib import Path

from market_morning_publisher.closing import (build_closing_input, render_closing_report,
                                               validate_closing_analysis)
from market_morning_publisher.closing_cli import quality_check


class ClosingReviewTests(unittest.TestCase):
    def setUp(self):
        self.payload = build_closing_input(Path("/tmp/nonexistent-mmp"), "2026-08-20", {
            "contract": "MMP_KOREA_CLOSE_V1", "report_date": "2026-08-20",
            "indices": [
                {"name": "KOSPI", "ok": True, "session_date": "2026-08-20", "open": 3200.0, "high": 3220.0, "low": 3190.0, "close": 3210.0, "change_pct": 0.5},
                {"name": "KOSDAQ", "ok": True, "session_date": "2026-08-20", "open": 800.0, "high": 810.0, "low": 795.0, "close": 805.0, "change_pct": -0.2},
            ]}, [], datetime(2026, 8, 20, 8, tzinfo=timezone.utc))
        self.analysis = {
            "schema_version": "1.0", "insight_version": self.payload["insight_version"],
            "report_date": "2026-08-20", "as_of_kst": "2026-08-20T17:00:00+09:00",
            "one_line_diagnosis": "지수 반응만 확인됐다.", "overall_confidence": "LOW",
            "market_review": {"facts": ["종가 확인"], "interpretation": ["혼조"], "hypothesis": ["수급 확인 필요"]},
            "prediction_evaluations": [{"prediction": "아침 전망 없음", "result": "NOT_EVALUABLE", "evidence": "분석 실패", "lesson": "복구 필요"}],
            "news_reactions": [], "mi_evaluations": [], "differences": ["비교 불가"],
            "carry_forward": ["수급 확인"], "missing_data": ["투자자별 수급"], "invalidation_conditions": ["종가 정정"]}

    def test_missing_morning_is_explicitly_not_evaluable(self):
        validate_closing_analysis(self.analysis, self.payload)
        self.assertFalse(self.payload["morning_available"])

    def test_render_and_quality_gate(self):
        report = render_closing_report(self.analysis, self.payload)
        result = quality_check(self.payload, self.analysis, {"status": "COMPLETED"}, report)
        self.assertTrue(result["passed"])
        self.assertIn("투자 권유가 아닙니다", report)

    def test_wrong_session_date_blocks_publication(self):
        self.payload["actual_korea_close"]["indices"][0]["session_date"] = "2026-08-19"
        report = render_closing_report(self.analysis, self.payload)
        self.assertFalse(quality_check(self.payload, self.analysis, {"status": "COMPLETED"}, report)["passed"])

    def test_sample_investor_flow_is_not_accepted_as_full_market(self):
        from unittest.mock import patch
        from market_morning_publisher.closing import collect_korea_close
        sample = {"investor_flows": {"symbols": 73, "foreign_net_value": 5445}}
        with patch("market_morning_publisher.closing.load_json", return_value=sample), patch("market_morning_publisher.closing.fetch", side_effect=RuntimeError("offline")):
            result = collect_korea_close("2026-08-20", Path("sample.json"))
        self.assertIsNone(result["investor_flows"])


if __name__ == "__main__":
    unittest.main()

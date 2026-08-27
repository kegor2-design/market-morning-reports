import json
import unittest
from pathlib import Path

from market_morning_publisher.youtube_chart.claim_validation import (
    assess_claim,
    classify_claim_nature,
    contextual_excerpt,
    detect_pattern_candidates,
    merge_caption_texts,
    summarize_ocr,
)
from market_morning_publisher.youtube_chart.captions import CaptionCue


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/youtube_chart_validation.json").read_text(encoding="utf-8"))


def claim(text, *, categories=None):
    return {
        "source_claim_id": "YTC-0123456789ABCDEF0123",
        "channel_id": "park",
        "video_id": "abc",
        "timestamp_url": "https://www.youtube.com/watch?v=abc&t=1s",
        "speech_excerpt": text,
        "claim_categories": categories or [],
        "direction": "LONG",
        "timeframe_spoken": "DAILY",
        "asset_candidates": [{"symbol": "005930.KS", "name": "삼성전자"}],
        "target_price": None,
        "invalidation_price": None,
        "publicly_actionable_at": "2026-08-16T09:30:00+00:00",
    }


class YoutubeChartClaimValidationTest(unittest.TestCase):
    def test_reconstructs_context_and_removes_rolling_duplicates(self):
        merged = merge_caption_texts([
            "기준으로 역사 신고가를 경신했고요.",
            "기준으로 역사 신고가를 경신했고요. 후에 아래로 빠지지 않고",
            "후에 아래로 빠지지 않고 옆으로 횡보를 했죠.",
        ])
        self.assertEqual(
            merged,
            "기준으로 역사 신고가를 경신했고요. 후에 아래로 빠지지 않고 옆으로 횡보를 했죠.",
        )
        self.assertEqual(
            merge_caption_texts(["가격이 회복할 수 있을까요? 가격이 회복할 수 있을까요? 가격이"]),
            "가격이 회복할 수 있을까요?",
        )

    def test_context_window_includes_surrounding_forecast(self):
        cues = [
            CaptionCue(0, 2_000, "이전 이야기"),
            CaptionCue(10_000, 12_000, "아직 신고가는 돌파하지 못하고"),
            CaptionCue(15_000, 17_000, "신고가 돌파는 이제 시간 문제입니다"),
            CaptionCue(60_000, 62_000, "다른 이야기"),
        ]
        context = contextual_excerpt(cues, start_ms=10_000, end_ms=12_000, before_ms=1_000, after_ms=10_000)
        self.assertIn("시간 문제", context)
        self.assertNotIn("다른 이야기", context)
        enriched = claim("아직 신고가는 돌파하지 못하고")
        enriched["validation_context_excerpt"] = context
        self.assertEqual(classify_claim_nature(enriched, CONFIG)["primary_type"], "FORECAST")

    def test_classifies_description_forecast_action_and_mixed(self):
        self.assertEqual(
            classify_claim_nature(claim("지난주 신고가를 기록했습니다"), CONFIG)["primary_type"],
            "DESCRIPTION",
        )
        self.assertEqual(
            classify_claim_nature(claim("앞으로 상승할 가능성이 있습니다"), CONFIG)["primary_type"],
            "FORECAST",
        )
        self.assertEqual(
            classify_claim_nature(claim("전고점을 돌파하면 매수합니다"), CONFIG)["primary_type"],
            "ACTION_RULE",
        )
        self.assertEqual(
            classify_claim_nature(claim("지난주 돌파했습니다 앞으로 상승할 가능성이 있습니다"), CONFIG)["primary_type"],
            "MIXED",
        )

    def test_pending_automatic_result_is_never_scoreable(self):
        result = assess_claim(claim("앞으로 상승할 가능성이 있습니다"), config=CONFIG)
        self.assertEqual(result["evaluation_mode"], "PENDING_HUMAN_REVIEW")
        self.assertIn("HUMAN_CONFIRMATION_REQUIRED", result["blocking_issues"])

    def test_confirmed_forecast_is_directional_shadow(self):
        review = {
            "review_status": "CONFIRMED",
            "claim_type": "FORECAST",
            "asset_symbol": "005930.KS",
            "timeframe": "DAILY",
            "direction": "LONG",
        }
        result = assess_claim(claim("앞으로 상승할 가능성이 있습니다"), config=CONFIG, review=review)
        self.assertEqual(result["evaluation_mode"], "DIRECTIONAL_SHADOW")
        self.assertEqual(result["resolved_asset_symbol"], "005930.KS")

    def test_binary_shadow_requires_both_confirmed_levels(self):
        review = {
            "review_status": "CONFIRMED",
            "claim_type": "ACTION_RULE",
            "asset_symbol": "005930.KS",
            "timeframe": "DAILY",
            "direction": "LONG",
            "target_price": 110,
            "invalidation_price": 95,
        }
        result = assess_claim(claim("돌파하면 매수합니다"), config=CONFIG, review=review)
        self.assertEqual(result["evaluation_mode"], "BINARY_SHADOW")

    def test_confirmed_description_is_excluded_from_hit_rate(self):
        review = {
            "review_status": "CONFIRMED",
            "claim_type": "DESCRIPTION",
            "direction": "NEUTRAL",
        }
        result = assess_claim(claim("지난주 신고가를 기록했습니다"), config=CONFIG, review=review)
        self.assertEqual(result["evaluation_mode"], "EXCLUDED_RETROSPECTIVE_DESCRIPTION")

    def test_mixed_claim_requires_atomic_split(self):
        review = {
            "review_status": "CONFIRMED",
            "claim_type": "MIXED",
            "asset_symbol": "005930.KS",
            "timeframe": "DAILY",
            "direction": "LONG",
        }
        result = assess_claim(claim("지난주 돌파했습니다 앞으로 상승할 가능성이 있습니다"), config=CONFIG, review=review)
        self.assertEqual(result["evaluation_mode"], "NOT_SCOREABLE")
        self.assertIn("ATOMIC_CLAIM_SPLIT_REQUIRED", result["blocking_issues"])

    def test_detects_time_correction_pattern_as_candidate_only(self):
        value = claim("신고가 이후 빠지지 않고 횡보했습니다", categories=["BREAKOUT", "RANGE"])
        rows = detect_pattern_candidates(value, config=CONFIG)
        self.assertEqual(rows[0]["pattern_id"], "CHART-CAND-001")
        self.assertEqual(rows[0]["match_status"], "AUTO_TEXT_CANDIDATE")
        self.assertFalse(rows[0]["independently_verified"])

    def test_rejected_claim_does_not_remain_a_pattern_candidate(self):
        value = claim("신고가 이후 빠지지 않고 횡보했습니다", categories=["BREAKOUT", "RANGE"])
        rows = detect_pattern_candidates(
            value,
            config=CONFIG,
            review={"review_status": "REJECTED", "claim_type": "DESCRIPTION"},
        )
        self.assertEqual(rows, [])

    def test_ocr_summary_accepts_server_high_axis_status(self):
        ocr = {
            "frames": [{
                "screen_fields": {
                    "asset_candidates": [{"symbol": "005930.KS"}],
                    "timeframe_candidates": [{"normalized": "DAILY"}],
                },
                "price_axis_fit": {"status": "HIGH"},
                "overlays": [{"semantic_status": "REVIEW_REQUIRED"}],
            }]
        }
        result = summarize_ocr(ocr)
        self.assertEqual(result["price_axis_fitted_frame_count"], 1)
        self.assertEqual(result["review_required_overlay_count"], 1)


if __name__ == "__main__":
    unittest.main()

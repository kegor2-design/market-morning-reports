import unittest

from market_morning_publisher.youtube_chart.captions import CaptionCue
from market_morning_publisher.youtube_chart.claims import extract_chart_claims, find_chart_spans


TERMS = {
    "claim_categories": {"SUPPORT": ["지지"], "VWAP": ["vwap"], "BREAKOUT": ["돌파"]},
    "directions": {"BULLISH": ["돌파", "회복"], "BEARISH": ["이탈"]},
    "timeframes": {"DAILY": ["일봉"]},
    "assets": [{"symbol": "^KS11", "name": "KOSPI", "aliases": ["코스피"]}],
}


class YoutubeChartClaimsTest(unittest.TestCase):
    def test_merges_nearby_chart_cues_and_extracts_candidates(self):
        cues = [
            CaptionCue(1_000, 3_000, "코스피 일봉 지지 2,700"),
            CaptionCue(8_000, 10_000, "돌파하면 상승"),
            CaptionCue(30_000, 32_000, "일반적인 이야기"),
        ]
        claims = extract_chart_claims(
            cues,
            video={"id": "abc", "channel_id": "park", "published_at": "2026-08-16T23:00:00+00:00"},
            terms=TERMS,
        )
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim["claim_categories"], ["SUPPORT", "BREAKOUT"])
        self.assertEqual(claim["asset_candidates"][0]["symbol"], "^KS11")
        self.assertEqual(claim["timeframe_spoken"], "DAILY")
        self.assertEqual(claim["numeric_mentions"][0]["value"], 2700)
        self.assertEqual(claim["direction"], "LONG")
        self.assertEqual(claim["publicly_actionable_at"], "2026-08-16T23:00:00+00:00")
        self.assertTrue(claim["source_claim_id"].startswith("YTC-"))

    def test_claim_id_is_stable(self):
        cue = [CaptionCue(1_000, 2_000, "VWAP 회복")]
        video = {"id": "abc", "channel_id": "alpha", "published_at": "2026-08-16T20:00:00Z"}
        first = extract_chart_claims(cue, video=video, terms=TERMS)[0]["source_claim_id"]
        second = extract_chart_claims(cue, video=video, terms=TERMS)[0]["source_claim_id"]
        self.assertEqual(first, second)

    def test_non_chart_cue_is_not_a_claim(self):
        spans = find_chart_spans([CaptionCue(0, 1_000, "오늘 날씨가 좋습니다")], TERMS)
        self.assertEqual(spans, [])


if __name__ == "__main__":
    unittest.main()


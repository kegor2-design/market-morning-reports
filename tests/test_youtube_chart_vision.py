import unittest

from market_morning_publisher.youtube_chart.vision import (
    OcrToken, extract_screen_fields, fit_price_axis, normalize_timeframe_label, parse_paddle_result,
    price_at_pixel, recognize_overlays,
)


def box(x, y):
    return ((x, y), (x + 40, y), (x + 40, y + 20), (x, y + 20))


class YoutubeChartVisionTest(unittest.TestCase):
    def test_normalizes_legacy_and_current_paddle_shapes(self):
        legacy = [[[[[0, 0], [10, 0], [10, 10], [0, 10]], ("VWAP", 0.91)]]]
        current = {"res": {"rec_texts": ["지지"], "rec_scores": [0.88], "rec_polys": [[[0, 0], [10, 0], [10, 10], [0, 10]]]}}
        self.assertEqual(parse_paddle_result(legacy)[0].text, "VWAP")
        self.assertEqual(parse_paddle_result(current)[0].text, "지지")

    def test_extracts_price_axis_timeframe_and_asset(self):
        tokens = [
            OcrToken("2,700", 0.9, box(800, 100)), OcrToken("2,650", 0.9, box(800, 200)),
            OcrToken("코스피 5분봉", 0.95, box(20, 20)),
            OcrToken("10:30", 0.9, box(300, 520)),
        ]
        result = extract_screen_fields(tokens, width=1000, height=600, assets=[{"symbol": "^KS11", "name": "KOSPI", "aliases": ["코스피"]}])
        self.assertEqual(len(result["price_axis_ticks"]), 2)
        self.assertEqual(result["asset_candidates"][0]["symbol"], "^KS11")
        self.assertTrue(result["timeframe_candidates"])
        self.assertEqual(result["timeframe_candidates"][0]["normalized"], "MINUTE_5")
        self.assertEqual(result["time_axis_labels"][0]["text"], "10:30")
        self.assertEqual(normalize_timeframe_label("일봉"), "DAILY")

    def test_fits_linear_price_axis_or_returns_unknown(self):
        fitted = fit_price_axis([
            {"pixel_y": 100, "value": 110, "confidence": 0.9},
            {"pixel_y": 200, "value": 100, "confidence": 0.9},
            {"pixel_y": 300, "value": 90, "confidence": 0.9},
        ])
        self.assertEqual(fitted["status"], "FITTED")
        self.assertEqual(fitted["scale"], "LINEAR")
        self.assertEqual(fit_price_axis([{"pixel_y": 1, "value": 2, "confidence": 0.9}])["status"], "UNKNOWN")
        self.assertAlmostEqual(price_at_pixel(fitted, 200), 100)

    def test_line_geometry_does_not_invent_support_or_resistance(self):
        tokens = [OcrToken("VWAP", 0.9, box(0, 0))]
        overlays = recognize_overlays(tokens, [{"orientation": "HORIZONTAL", "confidence": 0.8, "y1": 10, "y2": 10}])
        self.assertEqual(overlays[0]["kind"], "VWAP")
        self.assertEqual(overlays[1]["kind"], "HORIZONTAL_LEVEL")
        self.assertEqual(overlays[1]["semantic_status"], "REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()

import unittest

from market_morning_publisher.youtube_chart.captions import parse_vtt, timestamp_to_ms


class YoutubeChartCaptionsTest(unittest.TestCase):
    def test_parses_tags_identifiers_and_rolling_captions(self):
        raw = """WEBVTT
Kind: captions

cue-1
00:00:01.000 --> 00:00:03.000 align:start position:0%
<c>여기가 지지선입니다</c>

00:00:03.000 --> 00:00:05.500
여기가 지지선입니다 <00:00:04.000><c>거래량을 확인합니다</c>

NOTE generated note
ignored

00:00:06,000 --> 00:00:07,000
VWAP 회복
"""
        cues = parse_vtt(raw)
        self.assertEqual([cue.text for cue in cues], ["여기가 지지선입니다", "거래량을 확인합니다", "VWAP 회복"])
        self.assertEqual((cues[0].start_ms, cues[-1].end_ms), (1000, 7000))

    def test_drops_exact_duplicate_rolling_cue(self):
        raw = """WEBVTT

00:01.000 --> 00:02.000
support

00:02.000 --> 00:03.000
support
"""
        self.assertEqual(len(parse_vtt(raw)), 1)

    def test_timestamp_supports_hourless_and_hours(self):
        self.assertEqual(timestamp_to_ms("01:02.345"), 62_345)
        self.assertEqual(timestamp_to_ms("01:01:02,003"), 3_662_003)


if __name__ == "__main__":
    unittest.main()


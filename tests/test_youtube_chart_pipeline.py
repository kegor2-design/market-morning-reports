import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from market_morning_publisher.youtube_chart.pipeline import (
    PipelineOptions, YoutubeChartPipeline, metadata_date_kst, normalize_video_metadata,
    select_caption_file, upsert_jsonl,
)


class YoutubeChartPipelineTest(unittest.TestCase):
    def test_normalizes_live_metadata_without_fabricating_publication(self):
        result = normalize_video_metadata(
            {"id": "abc", "was_live": True, "release_timestamp": 1_700_000_000, "upload_date": "20231115"},
            {"id": "alpha", "name": "Alpha"},
        )
        self.assertIsNone(result["published_at"])
        self.assertIsNotNone(result["livestream_start_at"])
        self.assertEqual(metadata_date_kst(result), date(2023, 11, 15))

    def test_selects_preferred_caption_language(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "abc.en.vtt").write_text("WEBVTT")
            (root / "abc.ko.vtt").write_text("WEBVTT")
            self.assertEqual(select_caption_file(root, "abc", ["ko", "en"]).name, "abc.ko.vtt")

    def test_jsonl_upsert_is_idempotent(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "claims.jsonl"
            upsert_jsonl(path, [{"id": "a", "value": 1}], key="id")
            upsert_jsonl(path, [{"id": "a", "value": 2}, {"id": "b", "value": 3}], key="id")
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(rows, [{"id": "a", "value": 2}, {"id": "b", "value": 3}])

    def test_pipeline_import_does_not_require_ocr_packages(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "config/youtube_chart_channels.json").write_text(json.dumps({"channels": []}))
            (root / "config/youtube_chart_terms.json").write_text("{}")
            pipeline = YoutubeChartPipeline(root, PipelineOptions(target_date=date(2026, 8, 16)))
            self.assertEqual(pipeline.channels, [])
            manifest = pipeline.run()
            self.assertEqual(manifest["status"], "COMPLETED")
            self.assertTrue((root / "data/state/youtube_chart/manifests/2026-08-16.json").exists())

    def test_explicit_video_url_bypasses_channel_rediscovery(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "config/youtube_chart_channels.json").write_text(json.dumps({"channels": [{"id": "c", "enabled": False, "collection_url": "https://example.invalid/videos"}]}))
            (root / "config/youtube_chart_terms.json").write_text("{}")
            pipeline = YoutubeChartPipeline(root, PipelineOptions(target_date=date(2026, 8, 24), channel_ids=("c",), video_urls=("https://youtube.com/watch?v=abc",)))
            self.assertEqual(pipeline._video_urls(pipeline.channels[0]), ["https://youtube.com/watch?v=abc"])


if __name__ == "__main__":
    unittest.main()

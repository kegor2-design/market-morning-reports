#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

import youtube_transcript_collector as collector


class CollectorTest(unittest.TestCase):
    def test_safe_slug(self):
        self.assertEqual(collector.safe_slug(" KPunch 채널 "), "kpunch")
        self.assertEqual(collector.safe_slug("chesley.tv"), "chesley.tv")

    def test_latest_status_uses_last_valid_row(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"video_id": "a", "state": "FAILED", "attempt": 1}),
                        "not-json",
                        json.dumps(
                            {
                                "video_id": "a",
                                "state": "COMPLETED_WITH_SUBTITLE",
                                "attempt": 2,
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            latest = collector.latest_status_by_id(path)
            self.assertEqual(latest["a"]["state"], "COMPLETED_WITH_SUBTITLE")
            self.assertEqual(latest["a"]["attempt"], 2)

    def test_discover_files_distinguishes_metadata_and_subtitles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "x.info.json").write_text("{}", encoding="utf-8")
            (root / "x.description").write_text("description", encoding="utf-8")
            (root / "x.ko-orig.vtt").write_text("WEBVTT\n", encoding="utf-8")
            files = collector.discover_files(root)
            self.assertTrue(files["has_info_json"])
            self.assertTrue(files["has_description"])
            self.assertEqual(files["subtitle_count"], 1)


if __name__ == "__main__":
    unittest.main()

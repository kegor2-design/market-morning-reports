import json
import unittest
from pathlib import Path

from scripts.build_kpunch_insight_ledger import ROOT, indicator_snapshot, timestamp_seconds


class KpunchInsightLedgerTest(unittest.TestCase):
    def test_claim_ids_and_video_references_are_valid(self):
        config = json.loads((ROOT / "config/kpunch_insight_claims.json").read_text(encoding="utf-8"))
        metadata = {
            json.loads(line)["video_id"]
            for line in (ROOT / "youtube_sources/kpunch/video_metadata.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        ids = [claim["claim_id"] for claim in config["claims"]]
        self.assertEqual(len(ids), 13)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(video["video_id"] in metadata for claim in config["claims"] for video in claim["videos"]))

    def test_debt_snapshot_excludes_imf_forecast_years(self):
        snapshot = indicator_snapshot("kr_debt_gdp")
        self.assertIsNotNone(snapshot)
        self.assertLessEqual(int(snapshot["as_of"]), 2024)

    def test_known_transcript_anchor_has_timestamp(self):
        self.assertIsNotNone(timestamp_seconds("T5pON5iwG64", "금융 시장을 길들여"))


if __name__ == "__main__":
    unittest.main()

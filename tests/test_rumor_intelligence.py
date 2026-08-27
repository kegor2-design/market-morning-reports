import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

from market_morning_publisher.rumor_intelligence import normalize_candidate, ingest_rows, build_rumor_watch, write_ledger, read_ledger
from market_morning_publisher.source_registry import load_source_registry

UTC = timezone.utc


class RumorIntelligenceTest(unittest.TestCase):
    def test_normalize_youtube_expert(self):
        c = normalize_candidate({
            "platform": "YOUTUBE_EXPERT",
            "video_id": "abc",
            "channel": "macro-channel",
            "author": "named analyst",
            "text": "9월 환율 변곡 가능성",
        })
        self.assertTrue(c.attributable)
        self.assertEqual(c.source_type, "YOUTUBE_EXPERT")

    def test_ingest_and_persist(self):
        rows = [{
            "event_id": "EVT-FX-1",
            "source_type": "TELEGRAM",
            "message_id": "1",
            "channel": "a",
            "title": "달러 공급 지속설",
            "text": "9월에도 환전 지속",
            "event_type": "FX_FLOW"
        }]
        ledger = ingest_rows(rows, now=datetime(2026, 8, 25, tzinfo=UTC))
        self.assertEqual(len(ledger), 1)
        self.assertEqual(len(build_rumor_watch(ledger.values())), 1)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ledger.json"
            write_ledger(p, ledger.values(), generated_at=datetime(2026, 8, 25, tzinfo=UTC))
            loaded = read_ledger(p)
            self.assertEqual(set(loaded), set(ledger))
            raw = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(raw["contract"], "MMP_EVENT_LIFECYCLE_V1")


    def test_ingest_uses_source_registry_grouping(self):
        reg = load_source_registry("config/source_registry.json")
        rows = [
            {"event_id":"EVT-X", "source_type":"TELEGRAM", "message_id":"1", "channel":"@stockinfojji", "text":"claim", "title":"same", "event_type":"OTHER"},
            {"event_id":"EVT-X", "source_type":"TELEGRAM", "message_id":"2", "channel":"@stocknews_today", "text":"claim repost", "title":"same", "event_type":"OTHER"},
        ]
        ledger = ingest_rows(rows, now=datetime(2026,8,25,tzinfo=UTC), source_registry=reg)
        self.assertEqual(ledger["EVT-X"].status, "UNVERIFIED")
        self.assertEqual(len(ledger["EVT-X"].evidence), 2)

    def test_missing_source_id_rejected(self):
        with self.assertRaises(ValueError):
            normalize_candidate({"source_type": "TELEGRAM", "text": "claim"})


if __name__ == "__main__":
    unittest.main()

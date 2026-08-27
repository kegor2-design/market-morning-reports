import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

from market_morning_publisher.telegram_rumor_collector import normalize_message, load_config, write_jsonl

UTC = timezone.utc


class TelegramRumorCollectorTest(unittest.TestCase):
    def test_normalize_message(self):
        row = normalize_message(
            channel="@sample",
            message_id=123,
            text="시장 관련 주장",
            published_at=datetime(2026, 8, 25, 3, 0, tzinfo=UTC),
            title="Sample Channel",
            username="sample",
            views=100,
            forwards=2,
        )
        self.assertEqual(row["source_type"], "TELEGRAM_NAMED")
        self.assertEqual(row["message_id"], "123")
        self.assertEqual(row["url"], "https://t.me/sample/123")
        self.assertEqual(row["metadata"]["views"], 100)

    def test_config_contract(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cfg.json"
            p.write_text(json.dumps({"contract": "MMP_TELEGRAM_RUMOR_SOURCE_V1", "enabled": False, "sources": []}), encoding="utf-8")
            self.assertFalse(load_config(p)["enabled"])

    def test_write_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.jsonl"
            write_jsonl(p, [{"x": 1}, {"x": 2}])
            self.assertEqual(len(p.read_text(encoding="utf-8").splitlines()), 2)


if __name__ == "__main__":
    unittest.main()

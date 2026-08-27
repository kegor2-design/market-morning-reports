import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from market_morning_publisher.youtube_chart.validation_cli import (
    enrich_claim_contexts,
    initialize_review_template,
    run_validation,
)


CONFIG = {
    "schema_version": "1.0",
    "mode": "SHADOW_ONLY",
    "forward_windows": [1, 2],
    "horizon_bars": 2,
    "classification_terms": {
        "ACTION_RULE": ["매수"],
        "FORECAST": ["앞으로"],
        "CONDITION": ["하면"],
        "DESCRIPTION": ["지난"],
    },
    "pattern_candidates": [],
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def sample_claim():
    return {
        "source_claim_id": "YTC-0123456789ABCDEF0123",
        "channel_id": "park",
        "video_id": "abc",
        "timestamp_url": "https://www.youtube.com/watch?v=abc&t=1s",
        "speech_excerpt": "앞으로 상승할 가능성이 있습니다",
        "claim_categories": ["BREAKOUT"],
        "direction": "LONG",
        "timeframe_spoken": "DAILY",
        "asset_candidates": [{"symbol": "005930.KS", "name": "삼성전자"}],
        "target_price": None,
        "invalidation_price": None,
        "publicly_actionable_at": "2026-08-16T09:30:00+00:00",
    }


class YoutubeChartValidationCliTest(unittest.TestCase):
    def test_enriches_claim_from_raw_vtt_window(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            claim = sample_claim()
            claim["speech_start_ms"] = 10_000
            claim["speech_end_ms"] = 12_000
            claim["speech_excerpt"] = "아직 신고가는 돌파하지 못하고"
            caption = root / "data/private/youtube_chart/raw/park/abc/abc.ko-orig.vtt"
            caption.parent.mkdir(parents=True, exist_ok=True)
            caption.write_text(
                "WEBVTT\n\n00:10.000 --> 00:12.000\n아직 신고가는 돌파하지 못하고\n\n"
                "00:15.000 --> 00:17.000\n신고가 돌파는 이제 시간 문제입니다\n",
                encoding="utf-8",
            )
            config = {**CONFIG, "context_window": {"before_ms": 0, "after_ms": 10_000, "caption_priority": ["ko-orig"]}}
            enriched = enrich_claim_contexts(root, [claim], config)[0]
            self.assertEqual(enriched["validation_context_source"], "RAW_VTT_WINDOW")
            self.assertIn("시간 문제", enriched["validation_context_excerpt"])

    def test_initializes_editable_csv_without_overwriting_rows(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "reviews.csv"
            added = initialize_review_template(path, [sample_claim()], CONFIG)
            self.assertEqual(added, 1)
            self.assertEqual(initialize_review_template(path, [sample_claim()], CONFIG), 0)
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["review_status"], "PENDING")
            self.assertEqual(rows[0]["claim_type"], "FORECAST")

    def test_refreshes_pending_context_without_overwriting_human_fields(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "reviews.csv"
            initialize_review_template(path, [sample_claim()], CONFIG)
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
                fieldnames = list(rows[0])
            rows[0]["claim_type"] = "ACTION_RULE"
            rows[0]["asset_symbol"] = "^KS11"
            rows[0]["notes"] = "사람이 입력한 메모"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            enriched = sample_claim()
            enriched["validation_context_excerpt"] = "지난 움직임을 설명했습니다"
            self.assertEqual(initialize_review_template(path, [enriched], CONFIG), 0)
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                refreshed = list(csv.DictReader(handle))[0]
            self.assertEqual(refreshed["claim_type"], "ACTION_RULE")
            self.assertEqual(refreshed["asset_symbol"], "^KS11")
            self.assertEqual(refreshed["notes"], "사람이 입력한 메모")
            self.assertEqual(refreshed["auto_suggested_type"], "DESCRIPTION")
            self.assertIn("지난 움직임", refreshed["speech_excerpt"])

    def test_confirmed_binary_claim_uses_existing_ohlcv(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config/youtube_chart_validation.json"
            write_json(config_path, CONFIG)
            claim = sample_claim()
            write_jsonl(root / "data/normalized/youtube_chart/claims.jsonl", [claim])
            review_path = root / "data/state/youtube_chart/human_reviews.jsonl"
            write_jsonl(review_path, [{
                "review_version": "1.0",
                "source_claim_id": claim["source_claim_id"],
                "review_status": "CONFIRMED",
                "claim_type": "ACTION_RULE",
                "asset_symbol": "005930.KS",
                "timeframe": "DAILY",
                "direction": "LONG",
                "target_price": 110,
                "invalidation_price": 95,
                "pattern_ids": [],
            }])
            write_json(root / f"data/normalized/youtube_chart/ohlcv/{claim['source_claim_id']}.json", {
                "source_claim_id": claim["source_claim_id"],
                "symbol": "005930.KS",
                "interval": "1d",
                "bars": [
                    {"timestamp": "2026-08-16T09:00:00+00:00", "open": 99, "high": 101, "low": 98, "close": 100},
                    {"timestamp": "2026-08-16T10:00:00+00:00", "open": 100, "high": 103, "low": 97, "close": 102},
                    {"timestamp": "2026-08-16T11:00:00+00:00", "open": 102, "high": 111, "low": 101, "close": 109},
                ],
            })
            summary = run_validation(root, config_path=config_path, review_path=review_path)
            self.assertEqual(summary["human_review_counts"], {"CONFIRMED": 1})
            outcomes = [
                json.loads(line)
                for line in (root / "data/normalized/youtube_chart/validated_outcomes.jsonl").read_text().splitlines()
            ]
            self.assertEqual(outcomes[0]["status"], "SUCCESS")
            self.assertTrue((root / "data/state/youtube_chart/validation_report.md").exists())
            self.assertTrue((root / "data/state/youtube_chart/validation_review_packet.md").exists())

    def test_unreviewed_claim_is_not_evaluated(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config/youtube_chart_validation.json"
            write_json(config_path, CONFIG)
            write_jsonl(root / "data/normalized/youtube_chart/claims.jsonl", [sample_claim()])
            summary = run_validation(
                root,
                config_path=config_path,
                review_path=root / "data/state/youtube_chart/human_reviews.csv",
            )
            self.assertEqual(summary["evaluation_mode_counts"], {"PENDING_HUMAN_REVIEW": 1})
            self.assertEqual(summary["outcome_status_counts"], {"NOT_EVALUATED": 1})

    def test_fetches_confirmed_market_data_into_separate_reviewed_cache(self):
        class FakeClient:
            def fetch(self, symbol, *, start, end, interval):
                self.request = (symbol, interval)
                return [
                    {"timestamp": "2026-08-16T09:00:00+00:00", "open": 99, "high": 101, "low": 98, "close": 100},
                    {"timestamp": "2026-08-16T10:00:00+00:00", "open": 100, "high": 103, "low": 97, "close": 102},
                    {"timestamp": "2026-08-16T11:00:00+00:00", "open": 102, "high": 111, "low": 101, "close": 109},
                ]

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config/youtube_chart_validation.json"
            write_json(config_path, CONFIG)
            claim = sample_claim()
            write_jsonl(root / "data/normalized/youtube_chart/claims.jsonl", [claim])
            review_path = root / "data/state/youtube_chart/human_reviews.jsonl"
            write_jsonl(review_path, [{
                "source_claim_id": claim["source_claim_id"],
                "review_status": "CONFIRMED",
                "claim_type": "ACTION_RULE",
                "asset_symbol": "005930.KS",
                "timeframe": "DAILY",
                "direction": "LONG",
                "target_price": 110,
                "invalidation_price": 95,
            }])
            client = FakeClient()
            summary = run_validation(
                root,
                config_path=config_path,
                review_path=review_path,
                fetch_reviewed_ohlcv=True,
                ohlcv_client=client,
            )
            self.assertEqual(client.request, ("005930.KS", "1d"))
            self.assertEqual(summary["outcome_status_counts"], {"SUCCESS": 1})
            reviewed = root / f"data/normalized/youtube_chart/ohlcv_reviewed/{claim['source_claim_id']}.json"
            self.assertTrue(reviewed.exists())


if __name__ == "__main__":
    unittest.main()

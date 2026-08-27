import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from market_morning_publisher.nightly_youtube.synthesis import build_nightly_synthesis
from market_morning_publisher.youtube_insight.pipeline import (
    YoutubeInsightOptions,
    YoutubeInsightPipeline,
    _claim_to_card,
    _update_checkpoint,
)


class NightlyYoutubeTest(unittest.TestCase):
    def test_cross_channel_disagreement_is_preserved(self):
        channels = [
            {"id": "a", "name": "A", "tier": "T0", "role": "MACRO"},
            {"id": "b", "name": "B", "tier": "T1", "role": "EARNINGS"},
        ]
        claims = [
            {"claim_id": "1", "channel_id": "a", "channel_name": "A", "importance": "HIGH", "stance": "BEARISH", "issue_tags": ["US_TREASURY_STRESS"], "classification": "HYPOTHESIS", "claim_summary_ko": "금리 스트레스", "verification_status": "PARTIAL"},
            {"claim_id": "2", "channel_id": "b", "channel_name": "B", "importance": "HIGH", "stance": "BULLISH", "issue_tags": ["US_TREASURY_STRESS"], "classification": "HYPOTHESIS", "claim_summary_ko": "이익 견조", "verification_status": "PARTIAL"},
        ]
        result = build_nightly_synthesis("2026-08-24", claims, channels)
        self.assertEqual(result["disagreement_issue_count"], 1)
        self.assertFalse(result["issues"][0]["agreement"])
        self.assertTrue(result["issues"][0]["disagreement"])
        self.assertIn("not factual confirmation", result["fact_policy"])

    def test_cross_channel_agreement_requires_distinct_sources(self):
        channels = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        claims = [
            {"claim_id": "1", "channel_id": "a", "importance": "HIGH", "stance": "BEARISH", "issue_tags": ["AI_CAPEX"]},
            {"claim_id": "2", "channel_id": "b", "importance": "HIGH", "stance": "BEARISH", "issue_tags": ["AI_CAPEX"]},
        ]
        result = build_nightly_synthesis("2026-08-24", claims, channels)
        self.assertEqual(result["agreement_issue_count"], 1)
        self.assertEqual(result["issues"][0]["dominant_stance"], "BEARISH")

    def test_research_only_channel_never_auto_publishes(self):
        claim = {"claim_id": "x", "classification": "HYPOTHESIS", "importance": "CRITICAL", "confidence": "HIGH", "verification_status": "SUPPORTED", "chart_analysis_requested": False}
        video = {"id": "v", "title": "video"}
        channel = {"id": "cmt", "name": "CMT", "source_weight": "NORMAL", "research_only": True}
        card = _claim_to_card(claim, video, channel, {"minimum_importance": "HIGH"})
        self.assertFalse(card["publish_eligible"])
        self.assertEqual(card["publish_block_reason"], "RESEARCH_ONLY_SOURCE")

    def test_incremental_discovery_merges_sections_and_skips_checkpointed_video(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config").mkdir()
            (root / "config/youtube_insight_channels.json").write_text(json.dumps({
                "policy": {"bootstrap_lookback_hours": 48, "recovery_lookback_hours": 168, "max_recovery_lookback_hours": 720},
                "channels": [{"id": "x", "name": "X", "enabled": True, "collection_url": "u/videos", "collection_urls": [{"type": "videos", "url": "u/videos"}, {"type": "streams", "url": "u/streams"}], "max_videos_per_run": 5}],
            }), encoding="utf-8")
            for name in ("us_state_metrics.json", "us_issue_playbooks.json", "us_background_knowledge.json", "us_event_calendar.json", "insight_metric_registry.json", "insight_reasoning_playbooks.json", "insight_background_knowledge.json", "source_lenses.json"):
                (root / "config" / name).write_text("{}", encoding="utf-8")
            pipeline = YoutubeInsightPipeline(root, YoutubeInsightOptions(target_date=date(2026, 8, 24)))
            _update_checkpoint(root, pipeline.channels[0], [{"id": "old", "published_at": "2026-08-24T00:00:00+00:00"}], target_date=date(2026, 8, 24))
            def fake_list(url, **kwargs):
                if url.endswith("videos"):
                    return [{"id": "old", "timestamp": int(datetime(2026, 8, 24, 0, tzinfo=timezone.utc).timestamp())}, {"id": "new", "timestamp": int(datetime(2026, 8, 24, 1, tzinfo=timezone.utc).timestamp())}]
                return [{"id": "new", "timestamp": int(datetime(2026, 8, 24, 1, tzinfo=timezone.utc).timestamp())}, {"id": "live", "timestamp": int(datetime(2026, 8, 24, 2, tzinfo=timezone.utc).timestamp())}]
            with patch("market_morning_publisher.youtube_insight.pipeline.list_channel_videos", side_effect=fake_list):
                rows = pipeline._discover(pipeline.channels[0])
            self.assertEqual({row["id"] for row in rows}, {"new", "live"})
            self.assertEqual(len(rows), 2)

    def test_release_watchlist_has_multiple_sections_and_research_expansion(self):
        root = Path(__file__).resolve().parents[1]
        cfg = json.loads((root / "config/youtube_insight_channels.json").read_text(encoding="utf-8"))
        by_id = {row["id"]: row for row in cfg["channels"]}
        for channel_id in ("kpunch", "chesley", "ap_investment", "alphatrends"):
            types = {row["type"] for row in by_id[channel_id]["collection_urls"]}
            self.assertTrue({"videos", "streams", "shorts"} <= types)
        for channel_id in ("cmt_association", "stockcharts_tv", "investors_business_daily"):
            self.assertTrue(by_id[channel_id]["enabled"])
            self.assertTrue(by_id[channel_id]["research_only"])

    def test_same_day_checkpoint_rerun_preserves_persisted_cards(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config").mkdir()
            (root / "data/normalized").mkdir(parents=True)
            (root / "config/youtube_insight_channels.json").write_text(json.dumps({
                "policy": {"mode": "SHADOW_ONLY", "minimum_importance": "HIGH", "max_cards_per_digest": 6, "allow_rumor_auto_publish": False},
                "channels": [{"id": "kpunch", "name": "P", "enabled": True, "collection_url": "x", "subtitle_languages": ["ko"], "source_weight": "HIGH_PROVISIONAL", "role": "MACRO"}],
            }), encoding="utf-8")
            for name, data in {
                "us_state_metrics.json": {"metrics": [{"id": "m"}]},
                "us_issue_playbooks.json": {"playbooks": [{"id": "P"}]},
                "us_background_knowledge.json": {"modules": []},
                "us_event_calendar.json": {"events": []},
            }.items():
                (root / "config" / name).write_text(json.dumps(data), encoding="utf-8")
            raw = root / "data/private/youtube_insight/raw/kpunch/v"
            raw.mkdir(parents=True)
            (raw / "v.ko.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n테스트\n", encoding="utf-8")
            (raw / "metadata.normalized.json").write_text(json.dumps({"id":"v","title":"t","webpage_url":"https://youtube.com/watch?v=v","published_at":"2026-08-24T01:00:00+00:00"}), encoding="utf-8")
            def analyzer(_root, _input):
                return ({"schema_version":"1.0","video_id":"v","claims":[{
                    "classification":"HYPOTHESIS","importance":"HIGH","confidence":"MEDIUM","speech_start_ms":1000,"speech_end_ms":2000,
                    "claim_summary_ko":"가설","card_title_ko":"카드","verification_status":"PARTIAL","verification_summary_ko":"부분",
                    "our_interpretation_ko":"추적","causal_chain":[],"data_needed":[],"metric_ids":[],"playbook_ids":[],"calendar_event_ids":[],
                    "events_to_watch":[],"korea_transmission_ko":"UNKNOWN","invalidation_conditions":[],"source_event_ids":[],"supported_by_state":True,
                    "counterevidence_ko":"","chart_analysis_requested":False,"stance":"UNKNOWN","issue_tags":[]
                }]}, {"status":"COMPLETED"})
            first = YoutubeInsightPipeline(root, YoutubeInsightOptions(target_date=date(2026,8,24)), analyzer=analyzer)
            first._discover = lambda channel: [{"id":"v"}]
            self.assertEqual(first.run()["cards_selected"], 1)
            second = YoutubeInsightPipeline(root, YoutubeInsightOptions(target_date=date(2026,8,24)), analyzer=lambda *_: (_ for _ in ()).throw(AssertionError("analyzer should not rerun")))
            second._discover = lambda channel: []
            result = second.run()
            self.assertEqual(result["cards_selected"], 1)
            self.assertEqual(result["claims_extracted_this_run"], 0)


if __name__ == "__main__":
    unittest.main()

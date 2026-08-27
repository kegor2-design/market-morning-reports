import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_morning_publisher.youtube_chart.captions import CaptionCue
from market_morning_publisher.youtube_insight.codex import YoutubeInsightCodexError, validate_result
from market_morning_publisher.youtube_insight.pipeline import (
    build_verification_rows, refresh_verification_queue,
    YoutubeInsightOptions,
    YoutubeInsightPipeline,
    _claim_to_card,
    chunk_cues,
    rank_cards,
)
from market_morning_publisher.youtube_insight.render import render_digest_markdown


class YoutubeInsightTest(unittest.TestCase):
    def test_chunk_cues_preserves_all_cues(self):
        cues = [CaptionCue(i * 1000, i * 1000 + 900, "시장 금리와 국채 수요를 확인합니다 " + ("x" * 200)) for i in range(20)]
        chunks = chunk_cues(cues, max_chars=1100)
        self.assertGreater(len(chunks), 1)
        self.assertEqual([cue for chunk in chunks for cue in chunk], cues)

    def test_rumor_is_not_auto_publishable_by_default(self):
        claim = {
            "claim_id": "YTI-1", "classification": "RUMOR", "importance": "CRITICAL", "confidence": "HIGH",
            "claim_summary_ko": "확인되지 않은 정책 소문", "verification_status": "UNVERIFIED",
            "chart_analysis_requested": False,
        }
        video = {"id": "v1", "title": "영상", "webpage_url": "https://youtube.com/watch?v=v1"}
        channel = {"id": "kpunch", "name": "박종훈의 지식한방", "source_weight": "HIGH_PROVISIONAL"}
        card = _claim_to_card(claim, video, channel, {"minimum_importance": "HIGH", "allow_rumor_auto_publish": False})
        self.assertFalse(card["publish_eligible"])
        self.assertEqual(card["verification_status"], "UNVERIFIED")
        self.assertEqual(card["publish_block_reason"], "RUMOR_AUTO_PUBLISH_DISABLED")

    def test_high_weight_hypothesis_can_be_published_as_hypothesis(self):
        claim = {
            "claim_id": "YTI-2", "classification": "HYPOTHESIS", "importance": "HIGH", "confidence": "MEDIUM",
            "claim_summary_ko": "장기금리 압력에 대응한 정책일 가능성", "verification_status": "PARTIAL",
            "verification_summary_ko": "장기금리가 최근 상승", "our_interpretation_ko": "가설로 추적",
            "chart_analysis_requested": False,
        }
        video = {"id": "v2", "title": "영상", "webpage_url": "https://youtube.com/watch?v=v2"}
        channel = {"id": "kpunch", "name": "박종훈의 지식한방", "source_weight": "HIGH_PROVISIONAL"}
        card = _claim_to_card(claim, video, channel, {"minimum_importance": "HIGH", "allow_rumor_auto_publish": False})
        self.assertTrue(card["publish_eligible"])
        self.assertEqual(card["classification"], "HYPOTHESIS")

    def test_fact_claim_requires_independent_support(self):
        claim = {
            "claim_id": "YTI-3", "classification": "FACT_CLAIM", "importance": "HIGH", "confidence": "HIGH",
            "claim_summary_ko": "정책 규모가 확대됐다", "source_event_ids": [], "supported_by_state": False,
            "verification_status": "UNKNOWN", "chart_analysis_requested": False,
        }
        video = {"id": "v3", "title": "영상", "webpage_url": "https://youtube.com/watch?v=v3"}
        channel = {"id": "kpunch", "name": "박종훈의 지식한방", "source_weight": "HIGH_PROVISIONAL"}
        card = _claim_to_card(claim, video, channel, {"minimum_importance": "HIGH"})
        self.assertFalse(card["publish_eligible"])
        self.assertEqual(card["publish_block_reason"], "FACT_CLAIM_LACKS_INDEPENDENT_SUPPORT")

    def test_chart_central_claim_waits_for_chart_evidence(self):
        claim = {
            "claim_id": "YTI-4", "classification": "FORECAST", "importance": "HIGH", "confidence": "MEDIUM",
            "claim_summary_ko": "전고점 돌파 여부가 중요", "verification_status": "PARTIAL",
            "chart_analysis_requested": True, "chart_evidence": {"available": True, "status": "PENDING"},
        }
        video = {"id": "v4", "title": "영상", "webpage_url": "https://youtube.com/watch?v=v4"}
        channel = {"id": "park", "name": "차트", "source_weight": "HIGH"}
        card = _claim_to_card(claim, video, channel, {"minimum_importance": "HIGH", "require_chart_when_central": True})
        self.assertFalse(card["publish_eligible"])
        self.assertEqual(card["publish_block_reason"], "CHART_EVIDENCE_PENDING")

    def test_rank_cards_prefers_critical_hypothesis(self):
        cards = [
            {"card_id": "A", "publish_eligible": True, "importance": "HIGH", "classification": "FACT_CLAIM", "confidence": "HIGH"},
            {"card_id": "B", "publish_eligible": True, "importance": "CRITICAL", "classification": "HYPOTHESIS", "confidence": "MEDIUM"},
            {"card_id": "C", "publish_eligible": False, "importance": "CRITICAL", "classification": "HYPOTHESIS", "confidence": "HIGH"},
        ]
        self.assertEqual([x["card_id"] for x in rank_cards(cards, 2)], ["B", "A"])

    def test_codex_result_cannot_reference_unknown_evidence(self):
        analysis_input = {
            "video": {"id": "abc"},
            "allowed_source_event_ids": ["EV-1"],
            "allowed_metric_ids": ["us_30y"],
            "allowed_playbook_ids": ["TREASURY_BUYBACK"],
            "allowed_calendar_event_ids": ["2026-11-03_midterm"],
        }
        output = {
            "schema_version": "1.0", "video_id": "abc", "claims": [{
                "classification": "HYPOTHESIS", "importance": "HIGH", "confidence": "MEDIUM",
                "speech_start_ms": 1000, "speech_end_ms": 2000,
                "source_event_ids": ["EV-UNKNOWN"], "metric_ids": ["us_30y"],
                "playbook_ids": ["TREASURY_BUYBACK"], "calendar_event_ids": [],
            }]
        }
        with self.assertRaises(YoutubeInsightCodexError):
            validate_result(output, analysis_input)

    def test_digest_explicitly_labels_unverified_source_type(self):
        cards = [{
            "title_ko": "정책 목적 가설", "channel_name": "박종훈의 지식한방", "video_title": "테스트",
            "video_url": "https://youtube.com/watch?v=abc", "classification": "HYPOTHESIS",
            "verification_status": "UNVERIFIED", "source_weight": "HIGH_PROVISIONAL", "source_view_ko": "가설 요약",
            "verification_summary_ko": "독립 증거 부족", "our_interpretation_ko": "추가 검증 필요",
            "causal_chain": [], "data_to_watch": [], "events_to_watch": [], "korea_transmission_ko": "확인 불가",
            "invalidation_conditions": [], "chart_analysis_requested": False,
        }]
        md = render_digest_markdown("2026-08-24", cards, {"videos_analyzed": 1})
        self.assertIn("분류: **가설**", md)
        self.assertIn("검증 상태: **미확인**", md)
        self.assertIn("출처의 주장을 확인된 사실로 자동 간주하지 않습니다", md)

    def test_verification_queue_marks_due_windows_without_claiming_result(self):
        claims = [{
            "claim_id": "YTI-VERIFY", "video_id": "abc", "channel_id": "kpunch",
            "classification": "FORECAST", "video_published_at": "2026-08-20T00:00:00+00:00",
            "metric_ids": ["us_30y"], "invalidation_conditions": ["금리 정상화"],
        }]
        state = {"metrics": {"us_30y": {"value": 5.1, "state": "RISING", "as_of": "2026-08-24"}}}
        rows = build_verification_rows(claims, state)
        self.assertEqual(rows[0]["windows"]["T1D"]["status"], "PENDING")
        import datetime as _dt
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "verification.jsonl"
            refreshed = refresh_verification_queue(
                path, rows, state, now=_dt.datetime(2026, 8, 24, tzinfo=_dt.timezone.utc)
            )
        self.assertEqual(refreshed[0]["review_status"], "DUE_FOR_REVIEW")
        self.assertEqual(refreshed[0]["windows"]["T1D"]["status"], "DUE_FOR_REVIEW")
        self.assertNotIn("SUPPORTED", json.dumps(refreshed[0]))


    def test_release_channel_registry_supports_content_and_chart_handoff(self):
        root = Path(__file__).resolve().parents[1]
        insight = json.loads((root / "config/youtube_insight_channels.json").read_text(encoding="utf-8"))
        chart = json.loads((root / "config/youtube_chart_channels.json").read_text(encoding="utf-8"))
        insight_ids = [row["id"] for row in insight["channels"]]
        chart_ids = {row["id"] for row in chart["channels"]}
        self.assertEqual(len(insight_ids), len(set(insight_ids)))
        for required in ("kpunch", "chesley", "ap_investment", "plainbagel", "park_chart_center", "alphatrends"):
            self.assertIn(required, insight_ids)
        for requestable in ("kpunch", "chesley", "ap_investment", "park_chart_center", "alphatrends"):
            self.assertIn(requestable, chart_ids)
        self.assertFalse(insight["policy"]["allow_rumor_auto_publish"])


    def test_pipeline_writes_shadow_digest_with_mock_analyzer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config").mkdir()
            (root / "data/normalized").mkdir(parents=True)
            (root / "config/youtube_insight_channels.json").write_text(json.dumps({
                "policy": {"mode": "SHADOW_ONLY", "minimum_importance": "HIGH", "max_cards_per_digest": 6, "allow_rumor_auto_publish": False},
                "channels": [{"id": "kpunch", "name": "박종훈", "enabled": True, "collection_url": "x", "subtitle_languages": ["ko"], "source_weight": "HIGH_PROVISIONAL", "role": "MACRO"}],
            }), encoding="utf-8")
            for name, data in {
                "us_state_metrics.json": {"metrics": [{"id": "us_30y"}]},
                "us_issue_playbooks.json": {"playbooks": [{"id": "TREASURY_BUYBACK"}]},
                "us_background_knowledge.json": {"modules": []},
                "us_event_calendar.json": {"events": [{"id": "election", "date": "2026-11-03"}]},
            }.items():
                (root / "config" / name).write_text(json.dumps(data), encoding="utf-8")
            raw = root / "data/private/youtube_insight/raw/kpunch/abc"
            raw.mkdir(parents=True)
            (raw / "abc.ko.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n장기금리 때문에 바이백을 확대했을 가능성을 봐야 합니다.\n", encoding="utf-8")
            (raw / "metadata.normalized.json").write_text(json.dumps({
                "id": "abc", "title": "바이백", "channel_id": "kpunch", "channel": "박종훈",
                "webpage_url": "https://youtube.com/watch?v=abc", "upload_date": "20260824",
                "published_at": "2026-08-24T01:00:00+00:00",
            }), encoding="utf-8")

            def analyzer(_root, analysis_input):
                return ({"schema_version": "1.0", "video_id": "abc", "claims": [{
                    "classification": "HYPOTHESIS", "importance": "HIGH", "confidence": "MEDIUM",
                    "speech_start_ms": 1000, "speech_end_ms": 4000, "claim_summary_ko": "장기금리 대응 가설",
                    "card_title_ko": "바이백은 장기금리 대응인가", "verification_status": "PARTIAL",
                    "verification_summary_ko": "확인할 데이터가 남아 있음", "our_interpretation_ko": "우선 가설로 추적",
                    "causal_chain": ["장기금리 상승", "정책 대응"], "data_needed": ["30년물 금리"], "metric_ids": ["us_30y"],
                    "playbook_ids": ["TREASURY_BUYBACK"], "calendar_event_ids": ["election"], "events_to_watch": ["중간선거"],
                    "korea_transmission_ko": "반도체 할인율 경로 확인", "invalidation_conditions": ["장기금리 자체 정상화"],
                    "source_event_ids": [], "supported_by_state": True, "counterevidence_ko": "", "chart_analysis_requested": False,
                }]}, {"status": "COMPLETED"})

            options = YoutubeInsightOptions(target_date=date(2026, 8, 24), collect=True, analyze=True)
            pipeline = YoutubeInsightPipeline(root, options, analyzer=analyzer)
            pipeline._discover = lambda channel: [{"id": "abc"}]
            result = pipeline.run()
            self.assertEqual(result["cards_selected"], 1)
            self.assertEqual(result["publication"]["status"], "SHADOW_READY")
            report = root / "reports/2026-08/2026-08-24-youtube-view-cards.md"
            self.assertTrue(report.exists())
            self.assertIn("바이백은 장기금리 대응인가", report.read_text(encoding="utf-8"))


    def test_chart_strategy_cannot_reference_unknown_primitive(self):
        from market_morning_publisher.youtube_insight.codex import validate_result, YoutubeInsightCodexError
        analysis_input={"video":{"id":"v"},"allowed_source_event_ids":[],"allowed_metric_ids":[],"allowed_playbook_ids":[],"allowed_calendar_event_ids":[],"allowed_chart_primitive_ids":["BREAKOUT"]}
        claim={"classification":"ACTION_RULE","importance":"HIGH","confidence":"HIGH","speech_start_ms":0,"speech_end_ms":1000,"source_event_ids":[],"metric_ids":[],"playbook_ids":[],"calendar_event_ids":[],"chart_strategy":{"primitive_candidates":["MADE_UP"]}}
        with self.assertRaises(YoutubeInsightCodexError):
            validate_result({"schema_version":"1.0","video_id":"v","claims":[claim]}, analysis_input)

if __name__ == "__main__":
    unittest.main()

import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_morning_publisher.codex_analysis import (
    INSIGHT_VERSION, CodexAnalysisError, build_codex_input, render_codex_report, run_codex_analysis,
    safe_codex_env, validate_codex_analysis, _front_news,
)
from market_morning_publisher.core import quality_check


def sample_analysis():
    review = {"title":"Fed", "facts":"금리 동결", "interpretation":"유동성 중립", "counterevidence":"물가 재상승 가능성", "korea_transmission":"환율과 성장주 할인율", "source_event_ids":["EVT-001"]}
    return {
        "schema_version":"1.3", "insight_version":INSIGHT_VERSION, "report_date":"2026-08-12",
        "as_of_kst":"2026-08-12T08:10:00+09:00", "data_quality_summary":"핵심 가격 완료, 일부 수급 누락",
        "one_line_diagnosis":"가격은 우호적이나 이익 확인이 필요", "overall_confidence":"MEDIUM",
        "regime":{"state":"RISK_ON_SELECTIVE", "change_from_prior":"UNKNOWN", "rationale":"확산 근거 부족", "components":[{"name":"PRICE_CONFIRMATION", "state":"IMPROVING", "reason":"핵심지수 상승"}]},
        "key_drivers":[review], "regional_reviews":[review], "macro_policy_reviews":[review],
        "korea_after_close_news":[{"title":"반도체 공급계약", "announced_at_kst":"전일 18:00", "facts":"공급계약 공시", "verification_level":"OFFICIAL", "positive_industries":["반도체"], "negative_industries":[], "next_session_impact":"관련 산업의 주문 기대를 확인", "confidence":"MEDIUM", "confirmation":"공시 원문과 계약 규모", "source_event_ids":["EVT-001"]}],
        "news_industry_impacts":[{"news_issue":"정책금리 동결", "positive_industries":["성장 산업"], "negative_industries":["은행"], "transmission_path":"할인율 부담은 제한되지만 은행의 이자 수익 확대 기대는 낮아질 수 있음", "horizon":"SWING_1_4W", "confidence":"MEDIUM", "confirmation":"시장금리와 이익 전망", "invalidation":"시장금리 급등", "source_event_ids":["EVT-001"]}],
        "industry_company_reviews":[{"title":"반도체", "facts":"뉴스 확인", "earnings_cycle":"UNKNOWN", "positive_view":"수요 개선 가능성", "negative_view":"재고 확인 필요", "current_judgment":"관찰", "korea_value_chain":"메모리", "confirmation":"주문", "invalidation":"가격 반락", "source_event_ids":["EVT-001"]}],
        "preopen_stock_candidates":[{"symbol":"005930", "name":"삼성전자", "market":"KOSPI", "status":"CONDITIONAL_WATCH", "linked_industries":["반도체"], "selection_reason":"기사 직접 언급", "evidence_strength":"DIRECT_MENTION_ONLY", "fundamental_score":40, "ap_preopen_check":"장중 거래대금과 산업 확산 확인 필요", "confirmation":"공시와 수급", "invalidation":"직접 사업 영향 근거 부재", "source_event_ids":["EVT-001"]}],
        "investment_committee":[{"issue":"금리", "positive_view":"동결", "negative_or_alternative_view":"인하 지연", "current_judgment":"중립", "required_confirmation":"채권·환율", "principle_ids":["MI-001"]}],
        "korea_market":{"kospi":"선별적 우호", "kosdaq":"확인 필요", "transmission_summary":"환율·외국인", "sectors":[{"name":"반도체", "stance":"WATCH", "horizon":"MULTI_HORIZON", "reason":"이익 확인 필요", "invalidation":"주문 둔화"}]},
        "scenarios":[
            {"horizon":"NEXT_SESSION", "base":"혼조", "bull":"확산", "bear":"환율 상승", "switch_conditions":"외국인 수급"},
            {"horizon":"SWING_1_4W", "base":"선별", "bull":"리비전 상향", "bear":"금리 상승", "switch_conditions":"이익 추정치"},
            {"horizon":"MEDIUM_1_6M", "base":"UNKNOWN", "bull":"사이클 개선", "bear":"수요 둔화", "switch_conditions":"주문·재고"},
        ],
        "watch_items":["원달러"], "missing_data":["외국인 선물"], "invalidation_conditions":["핵심지수 반락"],
        "applied_principles":[{"principle_id":"MI-001", "version":1, "effect":"LIMITS", "reason":"뉴스 단독 신호 금지"}],
        "candidate_views":["이익 리비전 확인 후 판단"],
        "event_summaries_ko":[{"event_id":"EVT-001", "summary_ko":"연준이 정책금리를 동결했다."}],
    }


def sample_input():
    event = {"event_id":"evt-1", "headline":"삼성전자 Fed decision", "verified":True, "countries":["KR"], "sources":[
        {"source":"Reuters", "feed":"Korea after-close corporate news", "source_mode":"direct", "title":"삼성전자 Decision", "url":"https://example.com/reuters"},
    ]}
    return build_codex_input(
        "2026-08-12", datetime(2026, 8, 11, 23, 10, tzinfo=timezone.utc),
        datetime(2026, 8, 11, 6, 30, tzinfo=timezone.utc), datetime(2026, 8, 11, 23, 10, tzinfo=timezone.utc),
        [event], [{"symbol":"^GSPC", "name":"S&P", "region":"미국", "ok":True, "value":1, "change_pct":1, "session_status":"COMPLETED", "as_of_kst":"now"}], {}, [{"source_id":"fed", "ok":True}], {"market_data_complete":True},
        equity_master=[{"symbol":"005930", "name":"삼성전자", "market":"KOSPI", "industry_larg_code":"0010"}],
    )


class CodexAnalysisTest(unittest.TestCase):
    def test_const_schema_properties_declare_types(self):
        schema_path = Path(__file__).resolve().parents[1] / "config/codex_analysis_schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        def assert_const_types(node):
            if isinstance(node, dict):
                if "const" in node:
                    self.assertIn("type", node)
                for value in node.values():
                    assert_const_types(value)
            elif isinstance(node, list):
                for value in node:
                    assert_const_types(value)

        assert_const_types(schema)

    def test_validate_and_render(self):
        analysis, payload = sample_analysis(), sample_input()
        validate_codex_analysis(analysis, payload)
        report = render_codex_report(analysis, payload)
        self.assertIn("# 우리의 모닝브리핑", report)
        self.assertIn("## 오늘의 운용회의", report)
        self.assertIn("## 주요 일정 캘린더", report)
        self.assertIn("Event Intelligence:", report)
        self.assertIn("## 주요 해외 언론사 기사", report)
        self.assertIn("## 주요 국내 언론사 기사", report)
        self.assertIn("## 국제정세·국내 국정회의 상시 점검", report)
        self.assertIn("## 장 마감 후 국내 주요 뉴스", report)
        self.assertIn("반도체 공급계약", report)
        self.assertIn("## 뉴스 기반 산업 영향", report)
        self.assertIn("## 장전 종목 관찰 후보", report)
        self.assertIn("005930", report)
        self.assertIn("성장 산업", report)
        self.assertIn("2026-11-03", report)
        self.assertIn("뉴스 경로: 직접 수집", report)
        self.assertIn("한글 요약: 연준이 정책금리를 동결했다.", report)
        self.assertIn("- 시장 국면:", report)
        self.assertIn("- 판단 근거:", report)
        self.assertIn("https://example.com/reuters", report)
        self.assertNotIn("## X 주요 뉴스", report)
        self.assertNotIn("체슬리 관점", report)
        self.assertIn("일부 업종 중심의 강세", report)
        self.assertIn("다음 거래일", report)
        self.assertNotIn("RISK_ON_SELECTIVE", report)
        self.assertNotIn("NEXT_SESSION", report)

    def test_unknown_event_is_rejected(self):
        analysis = sample_analysis()
        analysis["key_drivers"][0]["source_event_ids"] = ["invented"]
        with self.assertRaises(CodexAnalysisError):
            validate_codex_analysis(analysis, sample_input())

    def test_news_industry_impact_requires_an_affected_industry(self):
        analysis = sample_analysis()
        analysis["news_industry_impacts"][0]["positive_industries"] = []
        analysis["news_industry_impacts"][0]["negative_industries"] = []
        with self.assertRaises(CodexAnalysisError):
            validate_codex_analysis(analysis, sample_input())

    def test_unknown_news_industry_event_is_rejected(self):
        analysis = sample_analysis()
        analysis["news_industry_impacts"][0]["source_event_ids"] = ["EVT-999"]
        with self.assertRaises(CodexAnalysisError):
            validate_codex_analysis(analysis, sample_input())

    def test_after_close_news_must_use_domestic_after_close_event(self):
        analysis = sample_analysis()
        analysis["korea_after_close_news"][0]["source_event_ids"] = ["EVT-999"]
        with self.assertRaises(CodexAnalysisError):
            validate_codex_analysis(analysis, sample_input())

    def test_input_uses_short_stable_analysis_references(self):
        payload = sample_input()
        self.assertEqual(payload["verified_events"][0]["event_id"], "EVT-001")
        self.assertEqual(payload["verified_events"][0]["original_event_id"], "evt-1")
        self.assertEqual(payload["domestic_after_close_event_ids"], ["EVT-001"])

    def test_input_preserves_event_intelligence_as_first_class_context(self):
        event_intelligence = {
            "calendar": {
                "upcoming_events": [{
                    "event_id":"E1", "name":"NVIDIA 실적", "scheduled_at_kst":"2026-08-27T05:20:00+09:00",
                    "base_importance":"S+", "dynamic_importance":"S+", "hours_until":45,
                    "korea_transmission":"HBM → 한국 반도체", "status":"SCHEDULED"
                }],
                "critical_upcoming_events": [{"event_id":"E1"}],
            },
            "disclosures": {"rows": []},
        }
        base = sample_input()
        payload = build_codex_input(
            base["report_date"], datetime(2026, 8, 25, tzinfo=timezone.utc),
            datetime(2026, 8, 24, tzinfo=timezone.utc), datetime(2026, 8, 25, tzinfo=timezone.utc),
            [{
                "event_id":"evt-1", "verified":True, "countries":["KR"], "headline":"공식 중요공시",
                "sources":[{
                    "feed":"Korea after-close corporate news", "source_mode":"direct",
                    "source":"OpenDART", "title":"공식 중요공시", "url":"https://dart.fss.or.kr/"
                }]
            }],
            [], {}, [], {}, event_intelligence=event_intelligence,
        )
        self.assertEqual(payload["event_intelligence"]["calendar"]["upcoming_events"][0]["event_id"], "E1")
        report = render_codex_report(sample_analysis(), payload)
        self.assertIn("NVIDIA 실적", report)
        self.assertIn("HBM → 한국 반도체", report)

    def test_official_disclosure_is_reserved_without_falsely_marking_after_close(self):
        base = sample_input()
        disclosure = {
            "event_id": "DART-202608250001", "verified": True, "countries": ["KR"],
            "event_type": "OFFICIAL_DISCLOSURE", "headline": "코오롱인더 · 공급계약",
            "sources": [{
                "feed": "Korea official disclosure", "source_mode": "direct",
                "source": "OpenDART", "title": "공급계약",
                "url": "https://dart.fss.or.kr/", "published_at": "2026-08-25 시간 미제공"
            }],
        }
        payload = build_codex_input(
            base["report_date"], datetime(2026, 8, 25, tzinfo=timezone.utc),
            datetime(2026, 8, 24, tzinfo=timezone.utc), datetime(2026, 8, 25, tzinfo=timezone.utc),
            [disclosure], [], {}, [], {},
            event_intelligence={
                "calendar": {"upcoming_events": [], "critical_upcoming_events": []},
                "disclosures": {"rows": [{
                    "receipt_date": "2026-08-25", "importance": "S", "corp_name": "코오롱인더",
                    "symbol": "120110", "report_name": "공급계약", "category": "CONTRACT",
                    "is_correction": False, "fact_scope": "공시 제목·접수 사실까지만 자동 확정"
                }]},
            },
        )
        self.assertEqual(payload["official_disclosure_event_ids"], ["EVT-001"])
        self.assertEqual(payload["domestic_after_close_event_ids"], [])
        report = render_codex_report(sample_analysis(), payload)
        self.assertIn("최근 중요 공시", report)
        self.assertIn("코오롱인더", report)
        self.assertIn("장 마감 후 공시", report)

    def test_closed_day_does_not_create_after_close_candidates(self):
        payload = sample_input()
        payload = build_codex_input(
            payload["report_date"], datetime(2026, 8, 16, tzinfo=timezone.utc),
            datetime(2026, 8, 15, tzinfo=timezone.utc), datetime(2026, 8, 16, tzinfo=timezone.utc),
            [{"event_id":"evt-1", "verified":True, "countries":["KR"], "sources":[{"feed":"Korea after-close corporate news"}]}],
            [], {}, [], {}, market_session_expected=False,
        )
        self.assertEqual(payload["domestic_after_close_event_ids"], [])

    def test_closed_day_can_explicitly_include_domestic_news(self):
        payload = sample_input()
        payload = build_codex_input(
            payload["report_date"], datetime(2026, 8, 16, tzinfo=timezone.utc),
            datetime(2026, 8, 15, tzinfo=timezone.utc), datetime(2026, 8, 16, tzinfo=timezone.utc),
            [{"event_id":"evt-1", "verified":True, "countries":["KR"], "sources":[{"feed":"Korea after-close corporate news"}]}],
            [], {}, [], {}, market_session_expected=False, include_closed_day_domestic=True,
        )
        self.assertEqual(payload["domestic_after_close_event_ids"], ["EVT-001"])

    def test_named_external_lens_is_rejected(self):
        analysis = sample_analysis()
        analysis["one_line_diagnosis"] = "체슬리 관점 결론"
        with self.assertRaises(CodexAnalysisError):
            validate_codex_analysis(analysis, sample_input())

    def test_duplicate_ids_are_rejected_by_python_validator(self):
        analysis = sample_analysis()
        analysis["key_drivers"][0]["source_event_ids"] = ["evt-1", "evt-1"]
        with self.assertRaises(CodexAnalysisError):
            validate_codex_analysis(analysis, sample_input())

        analysis = sample_analysis()
        analysis["investment_committee"][0]["principle_ids"] = ["MI-001", "MI-001"]
        with self.assertRaises(CodexAnalysisError):
            validate_codex_analysis(analysis, sample_input())

    def test_safe_environment_excludes_publisher_secrets(self):
        env = safe_codex_env({"PATH":"/bin", "OPENAI_API_KEY":"openai", "BLOGGER_CLIENT_SECRET":"secret", "BLOGGER_REFRESH_TOKEN":"token"})
        self.assertEqual(env["CODEX_API_KEY"], "openai")
        self.assertNotIn("BLOGGER_CLIENT_SECRET", env)
        self.assertNotIn("BLOGGER_REFRESH_TOKEN", env)

    def test_codex_command_is_read_only_ephemeral_and_schema_bound(self):
        analysis = sample_analysis()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config").mkdir()
            (root / "config/codex_analysis_schema.json").write_text("{}")
            Path(root / "fake-codex").write_text("binary")
            def executor(command, **kwargs):
                output = Path(command[command.index("-o") + 1])
                output.write_text(json.dumps(analysis, ensure_ascii=False))
                self.assertIn("--ephemeral", command)
                self.assertIn("read-only", command)
                self.assertNotIn("BLOGGER_CLIENT_SECRET", kwargs["env"])
                return type("Result", (), {"returncode":0, "stderr":"", "stdout":""})()
            with patch.dict(os.environ, {"MMP_CODEX_BIN":str(root / "fake-codex")}, clear=False):
                result, meta = run_codex_analysis(root, sample_input(), executor=executor)
            self.assertEqual(result["schema_version"], "1.3")
            self.assertEqual(meta["status"], "COMPLETED")

    def test_quality_passes_only_with_valid_analysis_metadata(self):
        analysis = sample_analysis()
        markets = [
            {"symbol":symbol, "ok":True, "usable_for_score":True, "change_pct":1, "session_status":"COMPLETED"}
            for symbol in ("^GSPC", "^IXIC", "^SOX")
        ] + [{"symbol":"^VIX", "ok":True, "usable_for_score":False}]
        event = {"verified":True, "korea_transmission":"환율", "insight_evidence":{"principle_candidates":["MI-001"]}, "sources":[{"url":"https://example.com"}]}
        macro = {"series":{key:{"ok":True} for key in ("us_cpi_yoy", "fed_target_upper", "fed_target_lower")}}
        report = render_codex_report(analysis, sample_input())
        quality = quality_check([event], markets, [{"ok":True}], report, macro, analysis, {"status":"COMPLETED"})
        self.assertTrue(quality["passed"])

    def test_front_news_groups_articles_by_publisher(self):
        analysis = sample_analysis()
        analysis["event_summaries_ko"] = [
            {"event_id": event_id, "summary_ko":"요약"} for event_id in ("e1", "e2", "e3", "e4")
        ]
        events = []
        for event_id, publisher, suffix in (
            ("e1", "CNBC", "c1"), ("e2", "BBC", "b1"),
            ("e3", "CNBC", "c2"), ("e4", "BBC", "b2"),
        ):
            events.append({"event_id":event_id, "sources":[{
                "source":publisher, "source_mode":"direct", "title":suffix, "url":f"https://example.com/{suffix}"
            }]})
        report = _front_news(events, {x["event_id"]:x["summary_ko"] for x in analysis["event_summaries_ko"]})
        positions = [report.index(marker) for marker in ("c1]", "c2]", "b1]", "b2]")]
        self.assertEqual(positions, sorted(positions))

    def test_front_news_never_publishes_google_search_fallback(self):
        events = [{"event_id":"e1", "sources":[
            {"source":"Reuters", "source_mode":"search", "title":"relay", "url":"https://news.google.com/rss/articles/x"},
            {"source":"CNBC", "source_mode":"direct", "title":"direct", "url":"https://www.cnbc.com/direct"},
        ]}]
        rendered = _front_news(events, {"e1":"요약"})
        self.assertIn("https://www.cnbc.com/direct", rendered)
        self.assertNotIn("news.google.com", rendered)


if __name__ == "__main__":
    unittest.main()

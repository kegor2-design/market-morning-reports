import unittest
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_morning_publisher.core import (
    cluster_articles, collect_macro_indicators, collect_markets, filter_articles, is_trading_day, market_view, overnight_window,
    parse_feed, parse_president_briefings, quality_check, resolve_article_urls, resolve_google_news_url
)
from unittest.mock import patch


def completed_market(symbol, change=1.0):
    return {
        "symbol": symbol, "name": symbol, "ok": True, "value": 100.0,
        "change_pct": change, "session_status": "COMPLETED",
        "usable_for_score": True, "as_of_kst": "2026-08-12T05:00:00+09:00",
    }


class CoreTest(unittest.TestCase):
    def test_google_news_rpc_resolution_returns_publisher_url(self):
        page = '<div data-n-a-id="token" data-n-a-ts="123" data-n-a-sg="signature"></div>'
        rpc = '[["wrb.fr","Fbv4je","[\\"garturlres\\",\\"https://www.reuters.com/world/story/\\"]"]]'
        with patch("market_morning_publisher.core.fetch", side_effect=[page.encode(), rpc.encode()]):
            url = resolve_google_news_url("https://news.google.com/rss/articles/token?oc=5")
        self.assertEqual(url, "https://www.reuters.com/world/story/")

    def test_unresolved_google_news_article_is_not_exposed(self):
        articles = [{"source_id":"google", "article_id":"x", "url":"https://news.google.com/rss/articles/x"}]
        with patch("market_morning_publisher.core.resolve_google_news_url", return_value=None):
            resolved, failures = resolve_article_urls(articles)
        self.assertEqual(resolved, [])
        self.assertEqual(failures, 1)

    def test_parse_president_briefings_keeps_only_policy_meetings(self):
        raw = json.dumps({"data":{"list":[
            {"BBS_CD":"abc", "SUBJECT":"제35회 국무회의 결과 브리핑", "WRITE_DT":"2026-08-11 16:39:00.0", "CONTENTS":"중동전쟁 대응과 경제 정책을 보고했다."},
            {"BBS_CD":"def", "SUBJECT":"대통령 현장 방문", "WRITE_DT":"2026-08-11 12:00:00.0", "CONTENTS":"현장 일정"},
        ]}}, ensure_ascii=False).encode()
        items = parse_president_briefings(raw, {"id":"president", "name":"청와대", "priority":5})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source_mode"], "direct")
        self.assertEqual(items[0]["url"], "https://www.president.go.kr/briefings/abc")
        self.assertEqual(items[0]["published_at"], "2026-08-11T07:39:00+00:00")

    def test_feed_and_cluster(self):
        raw = b"<rss><channel><item><title>Federal Reserve policy decision</title><link>https://example/a</link><description>Monetary policy rate</description><pubDate>Tue, 11 Aug 2026 20:00:00 GMT</pubDate></item></channel></rss>"
        source = {"id":"fed", "name":"Fed", "country":"US", "tier":1}
        articles = parse_feed(raw, source)
        self.assertEqual(articles[0]["source_mode"], "direct")
        self.assertEqual(articles[0]["source_priority"], 10)
        relevant = filter_articles(articles, datetime(2026, 8, 12, tzinfo=timezone.utc))
        events = cluster_articles(relevant)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["korea_transmission"])
        self.assertTrue(events[0]["has_direct_source"])

    def test_verification_accepts_official_or_trusted_publisher(self):
        base = {"source_tier":2, "country":"US", "source_summary":"inflation rate", "market_terms":["inflation", "rate"],
                "published_at":"2026-08-11T20:00:00+00:00"}
        low_quality = [
            {**base, "article_id":"a", "source_id":"q1", "source_name":"Query 1", "publisher":"Site A", "title":"Inflation rate rises sharply", "url":"https://a"},
            {**base, "article_id":"b", "source_id":"q2", "source_name":"Query 2", "publisher":"Site B", "title":"Inflation rate rises sharply", "url":"https://b"},
        ]
        self.assertFalse(cluster_articles(low_quality)[0]["verified"])
        trusted = {**low_quality[1], "publisher":"Reuters"}
        self.assertTrue(cluster_articles([low_quality[0], trusted])[0]["verified"])
        self.assertTrue(cluster_articles([trusted])[0]["verified"])

    def test_korean_trusted_business_report_is_verified(self):
        article = {
            "source_tier":2, "country":"KR", "source_summary":"반도체 공급계약 공시",
            "market_terms":["반도체", "공급계약"], "published_at":"2026-08-11T10:00:00+00:00",
            "article_id":"kr-1", "source_id":"korea_after_close_corporate",
            "source_name":"Korea after-close corporate news", "source_mode":"search",
            "publisher":"연합뉴스", "title":"상장사 반도체 공급계약 공시", "url":"https://example.kr/a",
        }
        event = cluster_articles([article])[0]
        self.assertTrue(event["verified"])
        self.assertIn("국내 기업의 주문", event["korea_transmission"])

    def test_korean_after_close_terms_are_classified(self):
        article = {
            "source_id":"korea_after_close_corporate", "source_name":"Korea after-close corporate news",
            "source_tier":2, "source_mode":"search", "country":"KR", "publisher":"연합뉴스",
            "url":"https://example.kr/disclosure", "article_id":"kr-close-1",
            "title":"코스피 상장사 대규모 조선 수주 공급계약 공시", "source_summary":"전일 장 마감 후 발표",
            "published_at":"2026-08-11T10:00:00+00:00",
        }
        relevant = filter_articles(
            [article], datetime(2026, 8, 11, 23, 10, tzinfo=timezone.utc),
            window_start=datetime(2026, 8, 11, 6, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(len(relevant), 1)
        self.assertIn("공급계약", relevant[0]["market_terms"])
        self.assertIn("조선", relevant[0]["market_terms"])

    def test_korean_policy_meeting_is_classified_and_can_use_source_lookback(self):
        article = {
            "source_id":"president", "source_name":"청와대", "source_tier":1, "country":"KR",
            "publisher":"대한민국 청와대", "url":"https://president.go.kr/briefings/x", "article_id":"policy-1",
            "title":"제30회 국무회의 및 비상경제점검회의 결과", "source_summary":"경제성장전략과 수출 정책을 논의",
            "published_at":"2026-08-10T00:00:00+00:00", "lookback_hours":168,
        }
        relevant = filter_articles(
            [article], datetime(2026, 8, 16, tzinfo=timezone.utc),
            window_start=datetime(2026, 8, 15, tzinfo=timezone.utc),
        )
        self.assertEqual(len(relevant), 1)
        self.assertIn("국내 국정회의", relevant[0]["strategic_topics"])
        self.assertTrue(cluster_articles(relevant)[0]["verified"])

    def test_strategic_topic_does_not_treat_unrelated_tax_substring_as_us_election(self):
        article = {
            "source_id":"cnbc", "source_name":"CNBC", "source_tier":2, "country":"INTL",
            "publisher":"CNBC", "url":"https://example.com/champagne", "article_id":"champagne",
            "title":"Extreme heat changes Champagne taste", "source_summary":"Harvest begins early",
            "published_at":"2026-08-15T20:00:00+00:00",
        }
        relevant = filter_articles([article], datetime(2026, 8, 16, tzinfo=timezone.utc))
        self.assertEqual(relevant, [])

    def test_us_election_policy_requires_election_or_trump_policy_anchor(self):
        article = {
            "source_id":"cnbc", "source_name":"CNBC", "source_tier":2, "country":"US",
            "publisher":"CNBC", "url":"https://example.com/tariff", "article_id":"tariff",
            "title":"Trump tariff policy shapes the midterm election", "source_summary":"Treasury and tax policy",
            "published_at":"2026-08-15T20:00:00+00:00",
        }
        relevant = filter_articles([article], datetime(2026, 8, 16, tzinfo=timezone.utc))
        self.assertIn("미국 중간선거·정책", relevant[0]["strategic_topics"])

    def test_stale_and_operational_news_are_excluded(self):
        base = {"source_id":"ecb", "source_name":"ECB", "source_tier":1, "country":"EU", "url":"https://example/a", "source_summary":"", "article_id":"a"}
        operational = {**base, "title":"T2S is operating normally", "published_at":"2026-08-11T20:00:00+00:00"}
        stale = {**base, "article_id":"b", "title":"ECB monetary policy rate", "published_at":"2026-08-01T20:00:00+00:00"}
        self.assertEqual(filter_articles([operational, stale], datetime(2026, 8, 12, tzinfo=timezone.utc)), [])

    def test_overnight_window_uses_korean_close_and_includes_weekend(self):
        from zoneinfo import ZoneInfo
        kst = ZoneInfo("Asia/Seoul")
        start, end = overnight_window(datetime(2026, 8, 10, 8, 10, tzinfo=kst), kst)
        self.assertEqual(start.astimezone(kst).isoformat(), "2026-08-07T15:30:00+09:00")
        self.assertEqual(end.astimezone(kst).isoformat(), "2026-08-10T08:10:00+09:00")

    def test_holiday_uses_daily_window_and_next_open_accumulates(self):
        from zoneinfo import ZoneInfo
        kst = ZoneInfo("Asia/Seoul")
        holidays = {"2026-08-17"}
        start, end = overnight_window(datetime(2026, 8, 17, 8, 10, tzinfo=kst), kst, market_holidays=holidays)
        self.assertEqual(start.astimezone(kst).isoformat(), "2026-08-16T08:10:00+09:00")
        self.assertFalse(is_trading_day(datetime(2026, 8, 17).date(), holidays))
        start, end = overnight_window(datetime(2026, 8, 18, 8, 10, tzinfo=kst), kst, market_holidays=holidays)
        self.assertEqual(start.astimezone(kst).isoformat(), "2026-08-14T15:30:00+09:00")
        self.assertEqual(end.astimezone(kst).isoformat(), "2026-08-18T08:10:00+09:00")

    def test_overnight_window_caps_manual_afternoon_run_at_0810(self):
        from zoneinfo import ZoneInfo
        kst = ZoneInfo("Asia/Seoul")
        _, end = overnight_window(datetime(2026, 8, 12, 13, 5, tzinfo=kst), kst)
        self.assertEqual(end.astimezone(kst).isoformat(), "2026-08-12T08:10:00+09:00")

    def test_through_now_mode_keeps_manual_execution_time(self):
        from zoneinfo import ZoneInfo
        kst = ZoneInfo("Asia/Seoul")
        _, end = overnight_window(datetime(2026, 8, 12, 13, 5, tzinfo=kst), kst, cap_at_morning=False)
        self.assertEqual(end.astimezone(kst).isoformat(), "2026-08-12T13:05:00+09:00")

    def test_window_excludes_pre_close_article(self):
        base = {"source_id":"news", "source_name":"News", "source_tier":2, "country":"US",
                "url":"https://example/a", "source_summary":"inflation policy", "article_id":"a"}
        article = {**base, "title":"US inflation policy", "published_at":"2026-08-11T05:00:00+00:00"}
        reference = datetime(2026, 8, 11, 23, 10, tzinfo=timezone.utc)
        window_start = datetime(2026, 8, 11, 6, 30, tzinfo=timezone.utc)
        self.assertEqual(filter_articles([article], reference, 72, window_start), [])

    def test_market_view_requires_completed_core_set(self):
        complete = [completed_market("^GSPC"), completed_market("^IXIC"), completed_market("^SOX", 2)]
        view = market_view(complete)
        self.assertTrue(view["market_data_complete"])
        self.assertEqual(view["price_confirmation_state"], "RISK_ON")
        partial = complete[:-1]
        blocked = market_view(partial)
        self.assertFalse(blocked["market_data_complete"])
        self.assertEqual(blocked["price_confirmation_state"], "UNKNOWN")

    def test_macro_collection_calculates_yoy(self):
        rows = "observation_date,CPIAUCSL\n" + "\n".join(
            f"2025-{month:02d}-01,{100 + month}" for month in range(1, 13)
        ) + "\n2026-01-01,110\n"
        config = {"fred_series":[{"id":"us_cpi_yoy", "series_id":"CPIAUCSL", "transform":"yoy_pct", "lag":12}]}
        with patch("market_morning_publisher.core.fetch", return_value=rows.encode()):
            result = collect_macro_indicators(config)
        self.assertTrue(result["series"]["us_cpi_yoy"]["ok"])
        self.assertEqual(result["series"]["us_cpi_yoy"]["value"], 8.91)

    def test_market_collection_distinguishes_partial_and_completed(self):
        def payload(end):
            return json.dumps({"chart":{"result":[{"timestamp":[1786370400, 1786456800],
                "meta":{"regularMarketTime":1786478400, "marketState":"UNKNOWN", "currentTradingPeriod":{"regular":{"end":end}}},
                "indicators":{"quote":[{"close":[100.0, 101.0]}]}}]}}).encode()
        with patch("market_morning_publisher.core.fetch", return_value=payload(1786482000)):
            partial = collect_markets([{"symbol":"^GSPC", "name":"S&P"}], datetime.fromtimestamp(1786480000, timezone.utc))[0]
        with patch("market_morning_publisher.core.fetch", return_value=payload(1786482000)):
            completed = collect_markets([{"symbol":"^GSPC", "name":"S&P"}], datetime.fromtimestamp(1786483000, timezone.utc))[0]
        self.assertEqual(partial["session_status"], "PARTIAL")
        self.assertFalse(partial["usable_for_score"])
        self.assertEqual(completed["session_status"], "COMPLETED")
        self.assertTrue(completed["usable_for_score"])

    def test_quality_blocks_missing_event_and_partial_market(self):
        markets = [completed_market("^GSPC"), completed_market("^IXIC")]
        statuses = [{"source_id":"x", "ok":True}]
        view = market_view(markets)
        report = "## 판단 무효화 조건\n투자 권유가 아닙니다"
        quality = quality_check([], markets, statuses, report)
        self.assertFalse(quality["passed"])
        self.assertFalse(quality["checks"]["market_data_complete"])
        self.assertFalse(quality["checks"]["fresh_relevant_event"])

    def test_closed_day_does_not_publish_without_verified_news(self):
        markets = [completed_market("^GSPC"), completed_market("^IXIC"), completed_market("^SOX")]
        statuses = [{"source_id":"x", "ok":True}]
        unverified = {"verified":False, "korea_transmission":"환율", "insight_evidence":{"principle_candidates":["MI-001"]}, "sources":[{"url":"https://example.com"}]}
        report = "## 판단 무효화 조건\n투자 권유가 아닙니다"
        quality = quality_check([unverified], markets, statuses, report, market_session_expected=False)
        self.assertFalse(quality["passed"])
        self.assertFalse(quality["checks"]["verified_event"])

    def test_quality_blocks_when_configured_direct_sources_all_fail(self):
        markets = [completed_market("^GSPC"), completed_market("^IXIC"), completed_market("^SOX")]
        statuses = [
            {"source_id":"bbc", "source_mode":"direct", "ok":False, "items":0},
            {"source_id":"google", "source_mode":"search", "ok":True, "items":20},
        ]
        report = "## 판단 무효화 조건\n투자 권유가 아닙니다"
        quality = quality_check([], markets, statuses, report)
        self.assertFalse(quality["checks"]["at_least_one_direct_source_ok"])

    def test_quality_blocks_without_codex_even_when_collection_is_complete(self):
        markets = [completed_market("^GSPC"), completed_market("^IXIC"), completed_market("^SOX"),
                   {**completed_market("^VIX", -1), "usable_for_score": False}]
        event = {"headline":"Fed policy rate", "importance_score":60, "independent_source_count":1, "verified":True,
                 "verification_reason":"공식 1차 출처",
                 "market_terms":["policy", "rate"], "korea_transmission":"글로벌 금리와 국내 성장주",
                 "insight_evidence":{"principle_candidates":["MI-001"]},
                 "sources":[{"source":"Fed", "title":"Policy rate", "url":"https://example/a"}]}
        statuses = [{"source_id":"fed", "ok":True}]
        report = "## 판단 무효화 조건\n투자 권유가 아닙니다"
        macro = {"series": {key:{"ok":True} for key in ("us_cpi_yoy", "fed_target_upper", "fed_target_lower")}}
        quality = quality_check([event], markets, statuses, report, macro)
        self.assertFalse(quality["passed"])
        self.assertFalse(quality["checks"]["codex_analysis_complete"])


if __name__ == "__main__":
    unittest.main()

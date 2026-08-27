import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from market_morning_publisher.event_intelligence import (
    apply_dynamic_importance, merge_calendar, parse_bea_schedule_events, parse_ics_events,
    parse_fomc_schedule_events, parse_bok_calendar_events, parse_boj_schedule_events,
    parse_ecb_schedule_events, select_upcoming,
)


class EventIntelligenceTest(unittest.TestCase):
    def test_bls_ics_is_converted_to_kst_and_filtered(self):
        source = {
            "id": "BLS", "timezone": "America/New_York", "url": "https://www.bls.gov/schedule/news_release/bls.ics",
            "title_rules": [
                {"contains":"Consumer Price Index", "event_type":"US_CPI", "base_importance":"S+", "korea_relevance":5}
            ],
        }
        text = """BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:cpi-202609\nDTSTART;TZID=America/New_York:20260911T083000\nSUMMARY:Consumer Price Index for August 2026\nEND:VEVENT\nBEGIN:VEVENT\nUID:minor\nDTSTART;TZID=America/New_York:20260911T100000\nSUMMARY:Minor Release\nEND:VEVENT\nEND:VCALENDAR\n"""
        rows = parse_ics_events(text, source)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_type"], "US_CPI")
        self.assertEqual(rows[0]["scheduled_at_kst"], "2026-09-11T21:30:00+09:00")
        self.assertEqual(rows[0]["source_id"], "BLS")

    def test_bea_schedule_parser_keeps_pce_and_gdp(self):
        source = {
            "id":"BEA", "timezone":"America/New_York", "url":"https://www.bea.gov/news/schedule",
            "title_rules":[
                {"contains":"Personal Income and Outlays", "event_type":"US_PCE", "base_importance":"S+", "korea_relevance":5},
                {"contains":"GDP", "event_type":"US_GDP", "base_importance":"S", "korea_relevance":4},
            ],
        }
        html = """<table><tr><td>August 26 8:30 AM</td><td>News</td><td>GDP (Second Estimate) and Corporate Profits, 2nd Quarter 2026</td></tr>
        <tr><td>August 26 8:30 AM</td><td>News</td><td>Personal Income and Outlays, July 2026</td></tr>
        <tr><td>September 3 8:30 AM</td><td>News</td><td>Unrelated release</td></tr></table>"""
        rows = parse_bea_schedule_events(html, source, year=2026)
        self.assertEqual({x["event_type"] for x in rows}, {"US_PCE", "US_GDP"})
        self.assertTrue(all(x["scheduled_at_kst"].startswith("2026-08-26T21:30") for x in rows))

    def test_schedule_change_is_persisted_without_losing_identity(self):
        now = datetime(2026, 8, 25, 0, 0, tzinfo=ZoneInfo("UTC"))
        existing = [{"event_id":"E1", "name":"CPI", "scheduled_at_kst":"2026-09-11T21:30:00+09:00", "first_seen_at":"old"}]
        observed = [{"event_id":"E1", "name":"CPI", "scheduled_at_kst":"2026-09-12T21:30:00+09:00"}]
        merged = merge_calendar(existing, observed, now=now)
        self.assertEqual(merged[0]["previous_scheduled_at_kst"], "2026-09-11T21:30:00+09:00")
        self.assertEqual(merged[0]["status"], "SCHEDULE_CHANGED")
        self.assertEqual(merged[0]["first_seen_at"], "old")
        self.assertTrue(merged[0]["changed_at"])

    def test_fomc_official_page_parser_reuses_stable_seed_id(self):
        html = "<h4>2026 FOMC Meetings</h4><div>September</div><div>15-16*</div><h4>2025 FOMC Meetings</h4>"
        source = {"id":"FED", "url":"https://fed.example", "timezone":"America/New_York"}
        rows = parse_fomc_schedule_events(html, source, years=[2026])
        self.assertEqual(rows[0]["event_id"], "FED_FOMC_2026_09")
        self.assertEqual(rows[0]["scheduled_at_kst"][:16], "2026-09-17T03:00")
        self.assertIn("SEP", rows[0]["name"])

    def test_bok_monthly_calendar_parser(self):
        html = "<div>통화정책방향 회의</div><span>2026-08-27</span>"
        rows = parse_bok_calendar_events(html, {"url":"https://bok.example"})
        self.assertEqual(rows[0]["event_id"], "BOK_MPC_2026_08_27")
        self.assertEqual(rows[0]["time_precision"], "DATE_CONFIRMED_TIME_OPERATIONAL_DEFAULT")

    def test_boj_schedule_parser(self):
        html = "<h2>2026</h2><div>Sept. 17 (Thurs.), 18 (Fri.) | -</div><h2>2027</h2>"
        source = {"url":"https://boj.example"}
        rows = parse_boj_schedule_events(html, source, years=[2026])
        self.assertEqual(rows[0]["event_id"], "BOJ_MPM_2026_09_18")
        self.assertEqual(rows[0]["scheduled_at_kst"][:16], "2026-09-18T12:00")

    def test_ecb_schedule_parser_uses_day_two(self):
        html = "<div>10/09/2026 Governing Council of the ECB: monetary policy meeting in Berlin (Day 2), followed by press conference</div>"
        source = {"url":"https://ecb.example", "timezone":"Europe/Berlin"}
        rows = parse_ecb_schedule_events(html, source)
        self.assertEqual(rows[0]["event_id"], "ECB_MPC_2026_09_10")
        self.assertEqual(rows[0]["scheduled_at_kst"][:16], "2026-09-10T21:15")

    def test_imminent_korea_relevant_event_is_promoted(self):
        as_of = datetime(2026, 8, 25, 8, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        event = {"event_id":"E", "scheduled_at_kst":"2026-08-26T08:00:00+09:00", "base_importance":"S", "korea_relevance":5}
        ranked = apply_dynamic_importance(event, as_of_kst=as_of)
        self.assertEqual(ranked["dynamic_importance"], "S+")
        selected = select_upcoming([event], as_of_kst=as_of, horizon_days=7, limit=10)
        self.assertEqual(selected[0]["event_id"], "E")


if __name__ == "__main__":
    unittest.main()

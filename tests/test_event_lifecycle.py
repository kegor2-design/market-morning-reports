import unittest
from datetime import datetime, timedelta, timezone

from market_morning_publisher.event_lifecycle import EventRecord, merge_candidate, expire_or_resolve, project_calendar_item

UTC = timezone.utc


class EventLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 25, 4, 30, tzinfo=UTC)

    def test_one_rumor_stays_unverified(self):
        row = {
            "title": "ADR 환전 9월 지속설",
            "event_type": "FX_FLOW",
            "claim": "9월까지 환전이 이어진다는 주장",
            "source_type": "TELEGRAM_ANON",
            "source_id": "tg-1",
            "source_name": "channel-a"
        }
        ev = merge_candidate(None, row, now=self.now)
        self.assertEqual(ev.truth_class, "UNVERIFIED")
        self.assertEqual(ev.status, "UNVERIFIED")
        self.assertEqual(ev.confidence_band, "LOW")

    def test_two_independent_rumors_do_not_become_official(self):
        base = merge_candidate(None, {
            "title": "ADR 환전 9월 지속설",
            "event_type": "FX_FLOW",
            "claim": "주장 A",
            "source_type": "TELEGRAM",
            "source_id": "1",
            "source_name": "a",
        }, now=self.now)
        ev = merge_candidate(base, {
            "title": base.title,
            "event_type": base.event_type,
            "claim": "주장 B",
            "source_type": "YOUTUBE",
            "source_id": "2",
            "source_name": "b",
        }, now=self.now)
        self.assertEqual(ev.truth_class, "UNVERIFIED")
        self.assertEqual(ev.status, "CORROBORATED_UNVERIFIED")
        self.assertEqual(ev.confidence_band, "MEDIUM")


    def test_same_independence_group_does_not_corroborate(self):
        base = merge_candidate(None, {
            "title": "같은 계열 재전파", "event_type": "OTHER", "claim": "A",
            "source_type": "TELEGRAM", "source_id": "1", "source_name": "channel-a",
            "metadata": {"independence_group": "same-network", "corroboration_eligible": True},
        }, now=self.now)
        ev = merge_candidate(base, {
            "title": base.title, "event_type": base.event_type, "claim": "B",
            "source_type": "TELEGRAM", "source_id": "2", "source_name": "channel-b",
            "metadata": {"independence_group": "same-network", "corroboration_eligible": True},
        }, now=self.now)
        self.assertEqual(ev.status, "UNVERIFIED")

    def test_discovery_aggregator_does_not_count_as_corroboration(self):
        base = merge_candidate(None, {
            "title": "집계채널 재전파", "event_type": "OTHER", "claim": "A",
            "source_type": "TELEGRAM", "source_id": "1", "source_name": "direct-rumor",
            "metadata": {"independence_group": "direct-rumor", "corroboration_eligible": True},
        }, now=self.now)
        ev = merge_candidate(base, {
            "title": base.title, "event_type": base.event_type, "claim": "A repost",
            "source_type": "TELEGRAM", "source_id": "2", "source_name": "aggregator",
            "metadata": {"independence_group": "aggregator", "corroboration_eligible": False},
        }, now=self.now)
        self.assertEqual(ev.status, "UNVERIFIED")

    def test_official_support_promotes_active(self):
        base = merge_candidate(None, {
            "title": "환전 일정",
            "event_type": "FX_FLOW",
            "claim": "텔레그램 주장",
            "source_type": "TELEGRAM",
            "source_id": "1",
            "source_name": "a",
        }, now=self.now)
        ev = merge_candidate(base, {
            "title": base.title,
            "event_type": base.event_type,
            "evidence": [{
                "claim": "회사 공식 확인",
                "source_type": "COMPANY_IR",
                "source_id": "ir-1",
                "official": True,
                "stance": "SUPPORT"
            }]
        }, now=self.now)
        self.assertEqual(ev.truth_class, "OFFICIAL_FACT")
        self.assertEqual(ev.status, "ACTIVE")
        self.assertEqual(ev.confidence_band, "HIGH")

    def test_official_denial_rejects(self):
        base = merge_candidate(None, {
            "title": "인수설",
            "event_type": "MNA",
            "claim": "인수설",
            "source_type": "TELEGRAM",
            "source_id": "1",
        }, now=self.now)
        ev = merge_candidate(base, {
            "title": base.title,
            "event_type": base.event_type,
            "activate": False,
            "evidence": [{
                "claim": "사실무근",
                "source_type": "COMPANY_IR",
                "source_id": "ir-deny",
                "official": True,
                "stance": "DENY"
            }]
        }, now=self.now)
        self.assertEqual(ev.status, "REJECTED")

    def test_unverified_ttl_expires(self):
        ev = EventRecord(
            event_id="x", title="x", event_type="OTHER", status="UNVERIFIED", truth_class="UNVERIFIED",
            first_seen_at=(self.now - timedelta(hours=100)).isoformat()
        )
        ev = expire_or_resolve(ev, now=self.now, unverified_ttl_hours=72)
        self.assertEqual(ev.status, "EXPIRED")

    def test_estimated_end_requires_resolution_check_not_auto_resolve(self):
        ev = EventRecord(
            event_id="x", title="x", event_type="OTHER", status="ACTIVE", truth_class="OFFICIAL_FACT",
            estimated_end_date=(self.now - timedelta(hours=1)).isoformat(), first_seen_at=self.now.isoformat()
        )
        ev = expire_or_resolve(ev, now=self.now)
        self.assertEqual(ev.status, "RESOLVING")

    def test_calendar_marks_unverified(self):
        ev = EventRecord(event_id="x", title="x", event_type="OTHER", status="UNVERIFIED", truth_class="UNVERIFIED")
        item = project_calendar_item(ev)
        self.assertTrue(item["uncertain"])
        self.assertEqual(item["badge"], "미확인")


if __name__ == "__main__":
    unittest.main()

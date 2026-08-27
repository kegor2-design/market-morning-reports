from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from zoneinfo import ZoneInfo
import json

from market_morning_publisher.calendar_page import calendar_rows, render_calendar_page


class CalendarPageTest(TestCase):
    def test_dedicated_page_marks_today_and_keeps_event_detail(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "data/state/event_intelligence"
            state.mkdir(parents=True)
            (state / "calendar.json").write_text(json.dumps({"events": [{"event_id": "E1", "scheduled_at_kst": "2026-08-25T10:00:00+09:00", "name": "금통위", "korea_transmission": "금리와 환율 확인", "source_url": "https://example.com"}]}), encoding="utf-8")
            now = datetime(2026, 8, 25, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
            self.assertEqual(len(calendar_rows(root, now)), 1)
            html = render_calendar_page(root, now)
            self.assertIn("오늘", html)
            self.assertIn("금리와 환율 확인", html)
            self.assertIn("calendar-upcoming", html)

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from market_morning_publisher.rumor_extraction import extract_all, telegram_candidates, youtube_candidates
from market_morning_publisher.rumor_page import render_rumor_page


class RumorExtractionTest(TestCase):
    def test_extracts_checkable_telegram_and_youtube_claims(self):
        tg = telegram_candidates([{"channel":"@x","message_id":"1","text":"A사가 다음 달 대형 공급 계약을 발표할 가능성이 있다는 소문입니다.","source_type":"TELEGRAM_ANON"}])
        yt = youtube_candidates([{"claim_id":"c1","video_id":"v1","channel_name":"전문가","claim_summary_ko":"정부가 조만간 반도체 지원 정책을 발표할 가능성을 검토합니다."}])
        self.assertEqual(len(tg), 1)
        self.assertEqual(tg[0]["event_type"], "CONTRACT")
        self.assertEqual(len(yt), 1)
        self.assertEqual(yt[0]["source_type"], "YOUTUBE_EXPERT")

    def test_extract_all_writes_unified_input_and_page_cards(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "data/private/telegram/normalized/messages.jsonl"
            p.parent.mkdir(parents=True)
            p.write_text(json.dumps({"channel":"@x","message_id":"1","text":"A사가 다음 달 대형 공급 계약을 발표할 가능성이 있다는 소문입니다."}, ensure_ascii=False)+"\n", encoding="utf-8")
            result = extract_all(root)
            self.assertEqual(result["telegram"], 1)
            self.assertTrue((root / "data/normalized/rumor/events.jsonl").exists())
            state = root / "data/state/event_intelligence"; state.mkdir(parents=True)
            (state / "rumor_watch.json").write_text(json.dumps({"rows":[{"event_id":"e1","title":"계약설","badge":"미확인","status":"UNVERIFIED","confidence_band":"LOW","impact_summary":"확인 필요"}]}, ensure_ascii=False), encoding="utf-8")
            (state / "event_lifecycle.json").write_text(json.dumps({"events":[]}), encoding="utf-8")
            self.assertIn("계약설", render_rumor_page(root))

    def test_latest_daily_news_is_scanned_for_explicit_schedule(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized = root / "data/normalized"
            normalized.mkdir(parents=True)
            (normalized / "2026-08-27-events.json").write_text(json.dumps([{
                "event_id": "EVT-001",
                "headline": "9월 16일 FOMC에서 정책금리를 발표할 예정입니다.",
                "published_at": "2026-08-27T00:00:00Z",
            }], ensure_ascii=False), encoding="utf-8")
            result = extract_all(root)
            self.assertEqual(result["daily_news"], 1)
            rows = (root / "data/normalized/rumor/events.jsonl").read_text(encoding="utf-8")
            self.assertIn('"event_type": "FOMC"', rows)
            self.assertIn('"event_date": "2026-09-16"', rows)

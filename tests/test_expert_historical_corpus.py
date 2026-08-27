import json
import tempfile
import unittest
from pathlib import Path

from market_morning_publisher.expert_historical_corpus import (
    parse_vtt, parse_text_transcript, build_inventory, infer_video_id, ExpertDefinition, InventoryItem, inventory_summary,
    claim_from_llm, build_primitive_index, compare_claim_to_history, build_validation_queue,
)


SAMPLE = """WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n금리가 내려가면 할인율이 낮아집니다.\n\n00:00:03.000 --> 00:00:05.000\n금리가 내려가면 할인율이 낮아집니다.\n\n00:00:05.000 --> 00:00:07.000\n그러나 이익이 무너지면 다릅니다.\n"""


def raw_claim(**overrides):
    base = {
        "speaker": "박세익",
        "claim_text": "금리 하락만으로 매수하지 말고 이익 경로를 함께 본다",
        "claim_kind": "PRIMARY_EXPERT_RULE",
        "evidence_summary": "할인율과 이익을 함께 비교",
        "causal_chain": ["금리 하락", "할인율 하락", "밸류에이션 상승 여지"],
        "premise_metrics": ["금리", "12개월 선행 EPS"],
        "time_horizon": "MONTHS",
        "related_assets": ["KOSPI"],
        "related_entities": [],
        "topics": ["금리", "이익"],
        "expected_direction": {"KOSPI": "UP_CONDITIONAL"},
        "invalidation_conditions": ["이익 추정치 급락"],
        "primitive_key": "rates_and_earnings_joint_filter",
        "stance": "SUPPORT",
        "source_timestamp_start": "00:00:01.000",
        "source_timestamp_end": "00:00:07.000",
        "attribution_confidence": "HIGH"
    }
    base.update(overrides)
    return base


class ExpertHistoricalCorpusTest(unittest.TestCase):
    def test_vtt_parsing_dedupes_adjacent_rolling_caption(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.vtt"
            p.write_text(SAMPLE, encoding="utf-8")
            parsed = parse_vtt(p)
            self.assertEqual(len(parsed["segments"]), 2)
            self.assertIn("이익이 무너지면", parsed["plain_text"])

    def test_infer_video_id(self):
        self.assertEqual(infer_video_id("20260801_AbCdEfGhI12.ko.vtt"), "AbCdEfGhI12")

    def test_inventory_coverage_guard(self):
        e = ExpertDefinition("x", "x", (), (), 2, 2)
        rows = [InventoryItem("x", "a", "a.vtt", None, None, None, None), InventoryItem("x", "b", "b.vtt", None, None, None, None)]
        self.assertTrue(inventory_summary(e, rows)["coverage_pass"])

    def test_primary_claim_is_reusable(self):
        c = claim_from_llm("chesley_park_seik", "vid", "2026-01-01", raw_claim())
        self.assertTrue(c.reusable)
        self.assertEqual(c.primitive_key, "rates_and_earnings_joint_filter")

    def test_guest_claim_not_reusable(self):
        c = claim_from_llm("chesley_park_seik", "vid", "2026-01-01", raw_claim(claim_kind="GUEST_CLAIM"))
        self.assertFalse(c.reusable)

    def test_timestamps_required(self):
        with self.assertRaises(ValueError):
            claim_from_llm("x", "v", None, raw_claim(source_timestamp_start=""))

    def test_text_verified_claim_allows_missing_timestamp(self):
        c = claim_from_llm(
            "x", "v", None,
            raw_claim(source_timestamp_start="", source_timestamp_end=""),
            evidence_tier="TEXT_VERIFIED",
        )
        self.assertTrue(c.reusable)
        self.assertEqual(c.evidence_tier, "TEXT_VERIFIED")

    def test_normalized_txt_inventory_is_text_verified(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "AbCdEfGhI12.txt"
            p.write_text("VIDEO_ID: AbCdEfGhI12\nTITLE: sample\nUPLOAD_DATE: 20260102\n\n전체 자막 본문", encoding="utf-8")
            parsed = parse_text_transcript(p)
            self.assertEqual(parsed["embedded_metadata"]["video_id"], "AbCdEfGhI12")
            item = build_inventory("x", [p])[0]
            self.assertEqual(item.evidence_tier, "TEXT_VERIFIED")
            self.assertEqual(item.published_at, "2026-01-02")

    def test_primitive_index_groups_repeated_rule(self):
        a = claim_from_llm("x", "v1", "2025-01-01", raw_claim())
        b = claim_from_llm("x", "v2", "2026-01-01", raw_claim(claim_text="같은 원칙을 다시 강조", source_timestamp_start="00:10:00.000", source_timestamp_end="00:10:10.000"))
        idx = build_primitive_index([a, b])
        self.assertEqual(len(idx["primitives"]), 1)
        self.assertEqual(idx["primitives"][0]["claim_count"], 2)

    def test_delta_reinforced(self):
        a = claim_from_llm("x", "v1", "2025-01-01", raw_claim())
        b = claim_from_llm("x", "v2", "2026-01-01", raw_claim(claim_text="동일 원칙 재강조", source_timestamp_start="00:10:00.000", source_timestamp_end="00:10:10.000"))
        self.assertEqual(compare_claim_to_history(b, [a]), "REINFORCED")

    def test_delta_contradicted(self):
        a = claim_from_llm("x", "v1", "2025-01-01", raw_claim())
        b = claim_from_llm("x", "v2", "2026-01-01", raw_claim(stance="OPPOSE", source_timestamp_start="00:10:00.000", source_timestamp_end="00:10:10.000"))
        self.assertEqual(compare_claim_to_history(b, [a]), "CONTRADICTED")

    def test_validation_queue_is_point_in_time(self):
        c = claim_from_llm("x", "v", "2026-01-01", raw_claim())
        q = build_validation_queue([c])
        self.assertTrue(q[0]["point_in_time_required"])


if __name__ == "__main__":
    unittest.main()

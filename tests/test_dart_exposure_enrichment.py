import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from enrich_dart_equity_exposures import classify_exposure_context, discover_exposures


class DartExposureEnrichmentTest(unittest.TestCase):
    def test_taxonomy_discovery_keeps_evidence_excerpt(self):
        taxonomy = {"themes":[{"industry":"인공지능 반도체","roles":[{"role":"고대역폭메모리","keywords":["HBM","고대역폭메모리"]}]}]}
        rows = discover_exposures("주요 제품은 HBM과 메모리 반도체입니다.", taxonomy)
        self.assertEqual(rows[0]["industry"], "인공지능 반도체")
        self.assertIn("HBM", rows[0]["excerpt"])

    def test_ascii_keyword_does_not_match_inside_another_word(self):
        taxonomy = {"themes":[{"industry":"전력","roles":[{"role":"무정전전원장치","keywords":["UPS"]}]}]}
        self.assertEqual(discover_exposures("AI Upscaling Pro 기능", taxonomy), [])
        self.assertEqual(len(discover_exposures("데이터센터 UPS 설비", taxonomy)), 1)

    def test_context_separates_input_from_revenue_role(self):
        self.assertEqual(classify_exposure_context("주요 원재료 매입액과 구매처")[0], "INPUT_DEPENDENCY")
        self.assertEqual(classify_exposure_context("당사의 주요 제품을 생산ㆍ판매합니다")[0], "PRODUCER_SERVICE")

    def test_discovery_prefers_product_context_over_earlier_market_outlook(self):
        taxonomy = {"themes":[{"industry":"로봇","roles":[{"role":"산업용 로봇","keywords":["산업용 로봇"]}]}]}
        text = "산업용 로봇 시장 전망입니다. " + ("기타 설명 " * 80) + "당사의 주요 제품은 산업용 로봇입니다."
        row = discover_exposures(text, taxonomy)[0]
        self.assertEqual(row["exposure_relation"], "PRODUCER_SERVICE")

    def test_distant_product_heading_does_not_turn_unrelated_keyword_into_producer(self):
        taxonomy = {"themes":[{"industry":"자동차","roles":[{"role":"완성차","keywords":["완성차 제조"]}]}]}
        text = "주요 제품은 보안 소프트웨어입니다. " + ("별도 설명 " * 30) + "고객인 완성차 제조 회사의 시장 동향"
        row = discover_exposures(text, taxonomy)[0]
        self.assertNotEqual(row["exposure_relation"], "PRODUCER_SERVICE")


if __name__ == "__main__":
    unittest.main()

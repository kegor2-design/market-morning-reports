import io
import unittest
import zipfile

from market_morning_publisher.disclosure_intelligence import (
    classify_disclosure, disclosure_news_events, extract_dart_document_evidence, normalize_disclosure,
)


class DisclosureIntelligenceTest(unittest.TestCase):
    def test_material_disclosure_is_classified(self):
        result = classify_disclosure("단일판매ㆍ공급계약체결")
        self.assertEqual(result["category"], "CONTRACT")
        self.assertEqual(result["importance"], "S")
        self.assertIsNone(classify_disclosure("기업설명회(IR)개최"))

    def test_dart_is_primary_official_fact_and_symbol_can_map(self):
        raw = {
            "corp_cls":"Y", "corp_code":"00123456", "corp_name":"코오롱인더", "report_nm":"단일판매ㆍ공급계약체결",
            "rcept_no":"20260824001234", "rcept_dt":"20260824", "rm":"",
        }
        master = [{"symbol":"120110", "name":"코오롱인더", "market":"KOSPI", "dart_corp_code":"00123456"}]
        item = normalize_disclosure(raw, equity_master=master)
        self.assertEqual(item["symbol"], "120110")
        self.assertEqual(item["verification_level"], "OFFICIAL")
        self.assertEqual(item["source"], "OpenDART")
        self.assertIn("공시 제목과 접수 사실만", item["fact_scope"])
        events = disclosure_news_events([item])
        self.assertTrue(events[0]["verified"])
        self.assertEqual(events[0]["sources"][0]["source_mode"], "direct")
        self.assertEqual(events[0]["sources"][0]["feed"], "Korea official disclosure")
        self.assertTrue(events[0]["korea_transmission"])
        self.assertTrue(events[0]["insight_evidence"]["principle_candidates"])
        self.assertEqual(events[0]["sources"][0]["source_tier"], 1)

    def test_original_document_extracts_material_evidence_without_needing_ocr(self):
        body = """<html><body><table><tr><td>계약금액</td><td>50,000,000,000원</td></tr>
        <tr><td>최근매출액</td><td>500,000,000,000원</td></tr><tr><td>매출액 대비</td><td>10.0%</td></tr>
        <tr><td>계약기간</td><td>2026-08-25 ~ 2028-08-24</td></tr></table></body></html>""".encode()
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w") as zf:
            zf.writestr("filing.xml", body)
        evidence = extract_dart_document_evidence(
            bio.getvalue(), keywords=["계약금액", "최근매출액", "매출액 대비", "계약기간"]
        )
        self.assertIn("50,000,000,000원", evidence)
        self.assertIn("10.0%", evidence)
        self.assertIn("계약기간", evidence)

    def test_correction_is_flagged(self):
        raw = {
            "corp_cls":"K", "corp_code":"00000001", "corp_name":"테스트", "report_nm":"[기재정정] 유상증자결정",
            "rcept_no":"20260825000001", "rcept_dt":"20260825", "rm":"정",
        }
        item = normalize_disclosure(raw, equity_master=[])
        self.assertTrue(item["is_correction"])
        self.assertEqual(item["category"], "CAPITAL")


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_morning_publisher.equity_candidates import build_equity_candidate_pool


class EquityCandidatePoolTest(unittest.TestCase):
    def test_direct_mentions_are_selected_from_master_only(self):
        events = [{"event_id":"EVT-001", "headline":"삼성전자 신규 공급계약", "sources":[], "evidence_summary":[]}]
        master = [
            {"symbol":"005930", "name":"삼성전자", "market":"KOSPI", "industry_larg_code":"10"},
            {"symbol":"000660", "name":"SK하이닉스", "market":"KOSPI", "industry_larg_code":"10"},
        ]
        pool = build_equity_candidate_pool(events, master, [])
        self.assertEqual([x["symbol"] for x in pool], ["005930"])
        self.assertEqual(pool[0]["selection_basis"], "DIRECT_MENTION")

    def test_only_verified_exposures_can_expand_the_pool(self):
        events = [{"event_id":"EVT-001", "headline":"HBM 수요 확대", "sources":[], "evidence_summary":[]}]
        master = [{"symbol":"000660", "name":"SK하이닉스", "market":"KOSPI"}]
        base = {"symbol":"000660", "industry":"반도체", "value_chain_role":"HBM", "exposure_relation":"PRODUCER_SERVICE", "candidate_eligible":True, "match_keywords":["HBM"], "revenue_exposure_pct":None, "evidence_type":"COMPANY_IR", "evidence_url":"https://example.com", "evidence_date":"2026-08-01", "confidence":"HIGH"}
        self.assertEqual(build_equity_candidate_pool(events, master, [{**base, "evidence_status":"STALE"}]), [])
        pool = build_equity_candidate_pool(events, master, [{**base, "evidence_status":"VERIFIED"}])
        self.assertEqual(pool[0]["symbol"], "000660")
        self.assertEqual(pool[0]["selection_basis"], "VERIFIED_EXPOSURE")

    def test_verified_input_dependency_is_not_a_positive_candidate(self):
        events = [{"event_id":"EVT-001", "headline":"양극재 가격 상승", "sources":[], "evidence_summary":[]}]
        master = [{"symbol":"373220", "name":"LG에너지솔루션", "market":"KOSPI"}]
        exposure = {"symbol":"373220", "industry":"이차전지", "value_chain_role":"양극재", "exposure_relation":"INPUT_DEPENDENCY", "candidate_eligible":False, "match_keywords":["양극재"], "evidence_status":"VERIFIED"}
        self.assertEqual(build_equity_candidate_pool(events, master, [exposure]), [])

    def test_unknown_symbols_never_enter_pool(self):
        events = [{"event_id":"EVT-001", "headline":"가상기업 반도체 수주", "sources":[], "evidence_summary":[]}]
        self.assertEqual(build_equity_candidate_pool(events, [], []), [])

    def test_short_or_generic_names_do_not_false_match(self):
        events = [{"event_id":"EVT-001", "headline":"New global levels emerge", "sources":[], "evidence_summary":[]}]
        master = [
            {"symbol":"160550", "name":"NEW", "market":"KOSDAQ"},
            {"symbol":"006260", "name":"LS", "market":"KOSPI"},
            {"symbol":"001680", "name":"대상", "market":"KOSPI"},
        ]
        self.assertEqual(build_equity_candidate_pool(events, master, []), [])


if __name__ == "__main__":
    unittest.main()

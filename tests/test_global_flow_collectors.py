import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from market_morning_publisher.insight_engine.global_flow_collectors import (
    collect_global_flow_metrics,
    parse_mof_weekly_foreign_bond_flow,
    parse_tic_japan_holdings,
)


class GlobalFlowCollectorsTest(unittest.TestCase):
    def test_parse_mof_weekly_uses_outward_long_term_debt_net(self):
        csv_text = (
            "header,,,,,,,\n"
            "2026．8．2～8．8,1,2,3,4,5,\"16,367 \",7\n"
            "2026．8．9～8．15,1,2,3,4,5,\"-11,351 \",7\n"
        )
        points = parse_mof_weekly_foreign_bond_flow(csv_text.encode("cp932"))
        self.assertEqual(points[-1], {"date": "2026-08-15", "value": -11351.0})

    def test_parse_tic_table5_sorts_months(self):
        raw = b"Table 5\nCountry\t2026-06\t2026-05\nJapan\t1116.7\t1143.1\n"
        points = parse_tic_japan_holdings(raw)
        self.assertEqual(points[-1], {"date": "2026-06-01", "value": 1116.7})

    def test_collector_exposes_semantic_states_and_proxy_disclosure(self):
        fred = "DATE,S\n" + "\n".join(f"2026-07-{i:02d},{100+i}" for i in range(1, 29))
        mof = "2026．8．9～8．15,1,2,3,4,5,\"-11,351 \",7\n".encode("cp932")
        tic = b"Country\t2026-06\t2026-05\nJapan\t1116.7\t1143.1\n"

        def fake_fetch(url):
            if "week.csv" in url:
                return mof
            if "table5" in url:
                return tic
            return fred.replace(",S", ",DEXJPUS").encode()

        config = {"metrics": [
            {"id":"usd_jpy","provider":"fred","series_id":"DEXJPUS","name":"USDJPY","frequency":"daily","stale_days":9999},
            {"id":"jpy_fx_vol","provider":"derived_realized_vol","input":"usd_jpy","name":"vol","stale_days":9999,"proxy_disclosure":"realized, not implied"},
            {"id":"japan_foreign_bond_flow","provider":"mof_weekly","url":"week.csv","name":"flow","stale_days":9999},
            {"id":"japan_treasury_holdings","provider":"tic_table5","url":"table5","country":"Japan","name":"tic","stale_days":9999},
        ]}
        with TemporaryDirectory() as tmp:
            result = collect_global_flow_metrics(Path(tmp), config, fetcher=fake_fetch)
        self.assertEqual(result["metrics"]["japan_foreign_bond_flow"]["state"], "REPATRIATING")
        self.assertEqual(result["metrics"]["japan_treasury_holdings"]["state"], "FALLING")
        self.assertEqual(result["metrics"]["jpy_fx_vol"]["proxy_disclosure"], "realized, not implied")


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import date

from market_morning_publisher.market_history import drawdowns, parse_shiller_rows, shiller_date


class MarketHistoryTest(unittest.TestCase):
    def test_shiller_decimal_date(self):
        self.assertEqual(shiller_date(1871.01), date(1871, 1, 1))
        self.assertEqual(shiller_date(2026.12), date(2026, 12, 1))
        self.assertIsNone(shiller_date("Date"))

    def test_parse_rows_ignores_incomplete_trailing_row(self):
        rows = [
            [1871.01, 4.44, 0.26, 0.4, 12.46, 0, 5.32, 112.14],
            [1871.02, 4.50, 0.26, 0.4, 12.84, 0, 5.32, 110.29],
            [1871.03, "", "", "", "", "", "", ""],
        ]
        result = parse_shiller_rows(rows)
        self.assertEqual([row["date"] for row in result], ["1871-01-01", "1871-02-01"])

    def test_drawdown_uses_running_peak(self):
        self.assertEqual(drawdowns([100, 120, 90, 150]), [0.0, 0.0, -25.0, 0.0])

    def test_parse_rows_includes_valuation_and_forward_returns(self):
        row = [1881.01, 6.19, 0.27, 0.4, 9.42, 0, 3.7, 163.2, 0, 330.0, 0, 0, 18.5, 0, 20.1, 0, 0.0125, 0, 0, 0.115, -0.031, 0.146]
        result = parse_shiller_rows([row])[0]
        self.assertEqual(result["gs10_pct"], 3.7)
        self.assertEqual(result["cape"], 18.5)
        self.assertEqual(result["excess_cape_yield_pct"], 1.25)
        self.assertEqual(result["stock_real_return_10y_pct"], 11.5)
        self.assertEqual(result["bond_real_return_10y_pct"], -3.1)
        self.assertEqual(result["excess_real_return_10y_pct"], 14.6)


if __name__ == "__main__":
    unittest.main()

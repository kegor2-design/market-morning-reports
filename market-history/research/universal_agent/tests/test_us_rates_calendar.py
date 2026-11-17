import unittest

from universal_agent.us_rates_calendar import expected_observations, publication_metadata


class USRatesCalendarTests(unittest.TestCase):
    def test_memorial_day_excluded_but_adjacent_observations_kept(self):
        for series in ('UST_2Y', 'UST_10Y', 'NYFED_SOFR'):
            dates, closed = expected_observations('2018-05-01', '2018-05-31', series)
            self.assertEqual(closed, ['2018-05-28'])
            self.assertIn('2018-05-25', dates)
            self.assertIn('2018-05-29', dates)
            self.assertEqual(len(dates), 22)

    def test_other_holidays_and_years_are_reviewed(self):
        _, closed_2018 = expected_observations('2018-07-02', '2018-07-31', 'NYFED_SOFR')
        _, closed_2019 = expected_observations('2019-05-01', '2019-05-31', 'UST_2Y')
        self.assertEqual(closed_2018, ['2018-07-04'])
        self.assertEqual(closed_2019, ['2019-05-27'])
        with self.assertRaisesRegex(ValueError, 'No reviewed'):
            expected_observations('2020-05-01', '2020-05-31', 'NYFED_SOFR')

    def test_sofr_publication_lag_is_separate_from_observation(self):
        self.assertEqual(publication_metadata('NYFED_SOFR')['publication_lag'],
                         'next_business_day')
        self.assertIsNone(publication_metadata('NYFED_SOFR')['first_accessible_at'])


if __name__ == '__main__':
    unittest.main()

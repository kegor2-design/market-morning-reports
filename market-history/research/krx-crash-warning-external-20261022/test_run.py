"""Boundary checks for H.15 publication-time alignment."""
import unittest
import run


class ReleaseJoinTests(unittest.TestCase):
    def test_korean_close_never_sees_future_h15_release(self):
        observations = run.released_observations(run.load_h15())
        joined = run.join(["2010-01-04", "2026-10-20"], observations)
        self.assertEqual(joined[0]["obs"], "2009-12-30")
        self.assertEqual(joined[1]["obs"], "2026-10-16")
        for row in joined:
            self.assertLessEqual(row["release_utc"], row["signal_utc"])

    def test_no_later_observation_changes_prior_join(self):
        observations = run.released_observations(run.load_h15())
        before = run.join(["2020-03-02"], observations)
        after = run.join(["2020-03-02"], observations[:-100])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

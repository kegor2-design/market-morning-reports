import unittest

from market_morning_publisher.expert_local_index import score_sentence, split_sentences


class ExpertLocalIndexTest(unittest.TestCase):
    def test_reasoned_investment_sentence_is_selected(self):
        score, topics = score_sentence("금리가 하락하면 할인율이 낮아지기 때문에 이익이 유지되는 성장주를 매수할 수 있습니다.")
        self.assertGreaterEqual(score, 6)
        self.assertIn("rates_liquidity", topics)
        self.assertIn("earnings", topics)

    def test_subscription_sentence_is_excluded(self):
        score, _ = score_sentence("구독과 좋아요 알림 설정을 부탁드립니다.")
        self.assertEqual(score, 0)

    def test_sentence_split_preserves_long_korean_units(self):
        rows = split_sentences("금리가 오르면 할인율이 높아집니다. 따라서 이익도 함께 확인해야 합니다.")
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()

import unittest
from rejection_learning_shadow import evaluate


class RejectionLearningTests(unittest.TestCase):
    def test_reports_winners_and_missing_without_claiming_fills(self):
        result = evaluate([
            {"reason": "buy pressure", "price_at_rejection": 1,
             "observations": [{"minutes_after": 5, "price": 1.3}]},
            {"reason": "buy pressure", "price_at_rejection": 2,
             "observations": []},
        ])
        five = result["by_reason"]["buy pressure"]["horizons"]["5"]
        self.assertEqual(five["observed"], 1)
        self.assertEqual(five["missing"], 1)
        self.assertAlmostEqual(five["median_gross_pct"], 30)
        self.assertEqual(result["by_reason"]["buy pressure"]["horizons"]["15"]["observed"], 0)

    def test_rejects_invalid_prices(self):
        result = evaluate([{"reason": "unknown", "price_at_rejection": 0, "observations": []}])
        self.assertEqual(result["by_reason"]["unknown"]["eligible"], 0)


if __name__ == "__main__":
    unittest.main()

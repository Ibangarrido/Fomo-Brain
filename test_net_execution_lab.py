import unittest
from net_execution_lab import assess_net_entry

class NetExecutionLabTests(unittest.TestCase):
    def test_costs_can_reverse_gross_gain(self):
        x = assess_net_entry(10, 5, liquidity_eur=10000)
        self.assertFalse(x["allowed"])
        self.assertLess(x["net_pct"], 0)
    def test_good_scenario_still_not_verified_execution(self):
        x = assess_net_entry(10, 20, liquidity_eur=10000)
        self.assertTrue(x["allowed"])
        self.assertFalse(x["execution_verified"])
    def test_missing_liquidity_fails_closed(self):
        self.assertEqual(assess_net_entry(10, 20)["reason"], "liquidity_unverified")
    def test_position_liquidity_limit(self):
        self.assertEqual(assess_net_entry(10, 50, liquidity_eur=100)["reason"], "position_too_large_for_liquidity")
    def test_nan_and_negative_cost_rejected(self):
        self.assertFalse(assess_net_entry(10, float("nan"), liquidity_eur=10000)["allowed"])
        self.assertFalse(assess_net_entry(10, 20, fee_per_side=-0.1, liquidity_eur=10000)["allowed"])
    def test_net_below_gross(self):
        x = assess_net_entry(10, 20, liquidity_eur=10000)
        self.assertLess(x["net_pct"], 20)
if __name__ == "__main__":
    unittest.main()

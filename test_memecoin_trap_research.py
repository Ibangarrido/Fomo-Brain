import unittest
from memecoin_trap_research import assess


class TrapResearchTests(unittest.TestCase):
    def test_dump_and_thin_liquidity(self):
        pair = {"liquidity": {"usd": 9000}, "volume": {"m5": 30000},
                "txns": {"m5": {"buys": 5, "sells": 30}},
                "priceChange": {"m5": -50}}
        result = assess(pair)
        self.assertEqual(len(result["risk_flags"]), 3)
        self.assertFalse(result["is_fraud_verdict"])
        self.assertEqual(result["executable_exit"], "not_verified")

    def test_missing_inputs_not_safe(self):
        result = assess({})
        self.assertEqual(result["risk_flags"], [])
        self.assertIn("liquidity", result["unknown_inputs"])
        self.assertEqual(result["wallet_concentration"], "not_available")

    def test_invalid_nonfinite_inputs(self):
        result = assess({"liquidity": {"usd": "nan"},
                         "volume": {"m5": "inf"},
                         "priceChange": {"m5": "nan"}})
        self.assertIn("liquidity", result["unknown_inputs"])
        self.assertIn("volume_m5", result["unknown_inputs"])
        self.assertIn("price_change_m5", result["unknown_inputs"])


if __name__ == "__main__":
    unittest.main()

import unittest
from market_data_coverage import audit

class CoverageTests(unittest.TestCase):
    def test_complete_fresh_observation(self):
        data = {"price": .01, "liquidity_usd": 20000, "volume_5m_usd": 5000,
                "buys_5m": 60, "sells_5m": 40, "holders": 800, "provider_timestamp": 1000}
        result = audit(data, now=1050)
        self.assertEqual(result["status"], "COMPLETE_OBSERVATION")
        self.assertFalse(result["paper_fill_authorized"])
        self.assertFalse(result["exit_quote_verified"])

    def test_missing_holders_blocks_completeness(self):
        data = {"price": .01, "liquidity_usd": 20000, "volume_5m_usd": 5000,
                "buys_5m": 60, "sells_5m": 40, "provider_timestamp": 1000}
        result = audit(data, now=1050)
        self.assertIn("holders", result["missing_fields"])
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_stale_and_future_are_rejected(self):
        data = dict.fromkeys(("price", "liquidity_usd", "volume_5m_usd", "buys_5m", "sells_5m", "holders"), 1)
        data["provider_timestamp"] = 1000
        self.assertEqual(audit(data, now=1200)["freshness"], "STALE")
        self.assertEqual(audit(data, now=980)["freshness"], "FUTURE")

    def test_invalid_price_and_unverified_timestamp(self):
        data = dict.fromkeys(("price", "liquidity_usd", "volume_5m_usd", "buys_5m", "sells_5m", "holders"), 1)
        data["price"] = float("nan")
        self.assertIn("price", audit(data)["invalid_fields"])
        self.assertEqual(audit(data)["freshness"], "UNVERIFIED")

if __name__ == "__main__":
    unittest.main()

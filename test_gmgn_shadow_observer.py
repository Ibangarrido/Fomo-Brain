import unittest
import gmgn_shadow_observer as gmgn

class GMGNObserverTests(unittest.TestCase):
    def event(self):
        return {"wallet": "walletA", "chain": "solana", "tx_hash": "tx1",
                "token_address": "mint1", "side": "BUY", "block_timestamp": 1000,
                "observed_at": 1060, "price_usd": .001,
                "liquidity_usd": 15000, "transaction_verified": True}

    def test_accepts_verified_recent_trade_without_execution(self):
        result = gmgn.observe([self.event()])
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["accepted"][0]["detection_delay_seconds"], 60)
        self.assertFalse(result["accepted"][0]["execution_verified"])
        self.assertIsNone(result["accepted"][0]["realizable_proceeds_eur"])
        self.assertEqual(result["trade_executions"], 0)

    def test_rejects_unverified_stale_and_illiquid(self):
        for field, value, reason in (
            ("transaction_verified", False, "TRANSACTION_UNVERIFIED"),
            ("observed_at", 1201, "STALE_OR_FUTURE_TRANSACTION"),
            ("observed_at", 999, "STALE_OR_FUTURE_TRANSACTION"),
            ("liquidity_usd", 9999, "INSUFFICIENT_LIQUIDITY"),
            ("price_usd", float("nan"), "INVALID_NUMERIC_PRICE_USD"),
            ("wallet", "", "MISSING_IDENTITY"),
        ):
            event = self.event()
            event[field] = value
            self.assertEqual(gmgn.validate_trade_event(event)["reason"], reason)

    def test_duplicate_transactions_not_counted_twice(self):
        result = gmgn.observe([self.event(), self.event()])
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["rejected"], ["DUPLICATE_TRANSACTION"])

if __name__ == "__main__":
    unittest.main()

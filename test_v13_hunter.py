"""Offline checks for V13. Run: python -m unittest test_v13_hunter.py"""
import unittest
from datetime import datetime, timezone, timedelta
from v13_hunter import observe, report

NOW = datetime(2026, 10, 18, 16, 0, tzinfo=timezone.utc)

def pair(**overrides):
    p = {"chainId": "solana", "pairAddress": "pool", "baseToken": {"address": "mint", "symbol": "TEST"},
         "pairCreatedAt": int((NOW-timedelta(minutes=12)).timestamp()*1000),
         "liquidity": {"usd": 30000}, "marketCap": 200000,
         "volume": {"m5": 10000}, "priceUsd": "0.0002",
         "priceChange": {"m5": 12, "h1": 45},
         "txns": {"m5": {"buys": 36, "sells": 14}}}
    p.update(overrides)
    return p

class HunterTests(unittest.TestCase):
    def test_valid_market_not_auto_trade(self):
        r = observe(pair(), NOW)
        self.assertTrue(r["market_gates_pass"])
        self.assertFalse(r["entry_authorized"])
        self.assertEqual(r["signal"], "VIGILAR")

    def test_moonshot_is_late(self):
        r = observe(pair(priceChange={"m5": 20, "h1": 1439}), NOW)
        self.assertIn("LATE_OR_UNKNOWN_1H", r["blockers"])
        self.assertEqual(r["signal"], "DESCARTAR_ENTRADA")

    def test_low_liquidity_kept_for_research(self):
        r = report([pair(liquidity={"usd": 9000})], NOW)
        self.assertEqual(r["observed"], 1)
        self.assertEqual(r["entries"], 0)
        self.assertEqual(r["discovery_alerts"], 1)

    def test_unknown_market_values_never_pass(self):
        r = observe(pair(txns={"m5": {}}, priceChange={}), NOW)
        self.assertFalse(r["market_gates_pass"])
        self.assertFalse(r["entry_authorized"])

if __name__ == "__main__":
    unittest.main()

"""Offline checks for V13. Run: python -m unittest test_v13_hunter.py"""
import unittest
from datetime import datetime, timezone, timedelta
from v13_hunter import observe, report, trend_observation, continuation_observation, mature_continuation_observation
from v13_runner import WATCH

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
    def test_manual_watchlist_has_unique_token_addresses(self):
        self.assertEqual(len(WATCH), len(set(WATCH)))
        self.assertTrue(all(chain == "solana" and isinstance(address, str) and address for chain, address in WATCH))

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

    def test_four_hour_trend_requires_history(self):
        row = observe(pair(), NOW)
        r = trend_observation(row, [])
        self.assertFalse(r["trend_watch"])
        self.assertEqual(r["trend_signal"], "HISTORIAL_INSUFICIENTE")
        self.assertFalse(r["trend_entry_authorized"])

    def test_four_hour_and_fifteen_minute_observed_confirmation(self):
        row = observe(pair(), NOW)
        history = [
            {"chain": "solana", "address": "mint", "received_at":
             (NOW-timedelta(hours=4, minutes=30)).isoformat(), "price_usd": 0.0001},
            {"chain": "solana", "address": "mint", "received_at":
             (NOW-timedelta(minutes=15)).isoformat(), "price_usd": 0.00018},
        ]
        r = trend_observation(row, history)
        self.assertTrue(r["trend_data_sufficient"])
        self.assertTrue(r["trend_watch"])
        self.assertFalse(r["trend_entry_authorized"])

    def test_four_hour_downtrend_rejected(self):
        row = observe(pair(), NOW)
        history = [
            {"chain": "solana", "address": "mint", "received_at":
             (NOW-timedelta(hours=4, minutes=30)).isoformat(), "price_usd": 0.0004},
            {"chain": "solana", "address": "mint", "received_at":
             (NOW-timedelta(minutes=15)).isoformat(), "price_usd": 0.00018},
        ]
        self.assertFalse(trend_observation(row, history)["trend_watch"])

    def test_monaka_pressure_is_research_only(self):
        r = observe(pair(txns={"m5": {"buys": 665, "sells": 480}}), NOW)
        self.assertIn("BUY_PRESSURE_UNVERIFIED_OR_LOW", r["blockers"])
        c = continuation_observation(r, [])
        self.assertTrue(c["continuation_buy_pressure_research"])
        self.assertFalse(c["continuation_watch"])
        self.assertFalse(c["continuation_entry_authorized"])

    def test_continuation_needs_real_breakout_and_volume(self):
        row = observe(pair(priceUsd="0.0003", volume={"m5": 12000},
                           txns={"m5": {"buys": 60, "sells": 40}}), NOW)
        history = [
            {"chain": "solana", "address": "mint", "received_at":
             (NOW-timedelta(minutes=30)).isoformat(), "price_usd": 0.0002, "volume_5m_usd": 5000},
            {"chain": "solana", "address": "mint", "received_at":
             (NOW-timedelta(minutes=15)).isoformat(), "price_usd": 0.00025, "volume_5m_usd": 6000},
        ]
        c = continuation_observation(row, history)
        self.assertTrue(c["continuation_watch"])
        self.assertGreater(c["continuation_relative_volume"], 1.2)
        self.assertFalse(c["continuation_entry_authorized"])
        row["price_usd"] = 0.00024
        self.assertFalse(continuation_observation(row, history)["continuation_watch"])

    def test_continuation_blocks_illiquid_pump(self):
        row = observe(pair(priceUsd="0.0003", liquidity={"usd": 3000}), NOW)
        history = [
            {"chain": "solana", "address": "mint", "received_at":
             (NOW-timedelta(minutes=30)).isoformat(), "price_usd": 0.0002, "volume_5m_usd": 1000},
            {"chain": "solana", "address": "mint", "received_at":
             (NOW-timedelta(minutes=15)).isoformat(), "price_usd": 0.00025, "volume_5m_usd": 2000},
        ]
        self.assertFalse(continuation_observation(row, history)["continuation_watch"])

    def test_mature_continuation_requires_real_history(self):
        old = int((NOW-timedelta(hours=4)).timestamp()*1000)
        row = observe(pair(pairCreatedAt=old, priceUsd="0.0003"), NOW)
        self.assertFalse(mature_continuation_observation(row, [])["mature_watch"])
        history = [
            {"chain":"solana","address":"mint","received_at":(NOW-timedelta(minutes=45)).isoformat(),"price_usd":0.0002},
            {"chain":"solana","address":"mint","received_at":(NOW-timedelta(minutes=15)).isoformat(),"price_usd":0.00025},
        ]
        result = mature_continuation_observation(row, history)
        self.assertTrue(result["mature_watch"])
        self.assertFalse(result["mature_entry_authorized"])
        self.assertIn("PAIR_AGE_OUT_OF_RANGE", row["blockers"])

    def test_mature_rejects_overextended_and_illiquid(self):
        old = int((NOW-timedelta(hours=4)).timestamp()*1000)
        history = [
            {"chain":"solana","address":"mint","received_at":(NOW-timedelta(minutes=45)).isoformat(),"price_usd":0.0002},
            {"chain":"solana","address":"mint","received_at":(NOW-timedelta(minutes=15)).isoformat(),"price_usd":0.00025},
        ]
        row = observe(pair(pairCreatedAt=old, priceUsd="0.0003",
                           priceChange={"m5":12,"h1":200}), NOW)
        self.assertFalse(mature_continuation_observation(row, history)["mature_watch"])
        row = observe(pair(pairCreatedAt=old, priceUsd="0.0003",
                           liquidity={"usd":1000}), NOW)
        self.assertFalse(mature_continuation_observation(row, history)["mature_watch"])

    def test_unknown_market_values_never_pass(self):
        r = observe(pair(txns={"m5": {}}, priceChange={}), NOW)
        self.assertFalse(r["market_gates_pass"])
        self.assertFalse(r["entry_authorized"])

if __name__ == "__main__":
    unittest.main()

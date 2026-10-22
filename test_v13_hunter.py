"""Offline checks for V13. Run: python -m unittest test_v13_hunter.py"""
import unittest
from datetime import datetime, timezone, timedelta
from v13_hunter import observe, report, trend_observation, continuation_observation, mature_continuation_observation, dormant_wakeup_observation
from v13_runner import WATCH, SUPPORTED_CHAINS, unique_alert_tokens

NOW = datetime(2026, 10, 18, 16, 0, tzinfo=timezone.utc)

def pair(**overrides):
    p = {"chainId": "solana", "pairAddress": "pool", "baseToken": {"address": "mint", "pair": "pool", "symbol": "TEST"},
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
        self.assertTrue(all(chain in SUPPORTED_CHAINS and isinstance(address, str) and address for chain, address in WATCH))
        self.assertIn(("bsc", "0xaacbc156435dbab7815a61bccba1c827e52a7777"), WATCH)
        self.assertIn(("bsc", "0xb10b2c022a717a66fa627c9c9ce73779b5347777"), WATCH)

    def test_unique_alert_tokens_deduplicates_pools_without_hiding_alerts(self):
        rows = [
            {"chain": "solana", "address": "mint-a", "pair": "pool-1", "discovery_alert": True},
            {"chain": "solana", "address": "mint-a", "pair": "pool-2", "discovery_alert": True},
            {"chain": "solana", "address": "mint-b", "pair": "pool-3", "discovery_alert": True},
            {"chain": "solana", "address": "mint-c", "pair": "pool-4", "discovery_alert": False},
            {"chain": "bsc", "address": "mint-a", "pair": "pool-5", "discovery_alert": True},
        ]
        self.assertEqual(sum(bool(r["discovery_alert"]) for r in rows), 4)
        self.assertEqual(unique_alert_tokens(rows), 3)
        self.assertEqual(unique_alert_tokens([]), 0)

    def test_valid_market_not_auto_trade(self):
        r = observe(pair(), NOW)
        self.assertTrue(r["market_gates_pass"])
        self.assertFalse(r["entry_authorized"])
        self.assertEqual(r["signal"], "VIGILAR")

    def test_early_age_extended_to_ninety_minutes(self):
        age_75 = int((NOW-timedelta(minutes=75)).timestamp()*1000)
        age_95 = int((NOW-timedelta(minutes=95)).timestamp()*1000)
        self.assertTrue(observe(pair(pairCreatedAt=age_75), NOW)["market_gates_pass"])
        self.assertIn("PAIR_AGE_OUT_OF_RANGE", observe(pair(pairCreatedAt=age_95), NOW)["blockers"])

    def test_mature_age_extended_to_twelve_hours(self):
        history = [
            {"chain":"solana","address":"mint","pair":"pool","received_at":(NOW-timedelta(minutes=45)).isoformat(),"price_usd":0.0001},
            {"chain":"solana","address":"mint","pair":"pool","received_at":(NOW-timedelta(minutes=15)).isoformat(),"price_usd":0.00015},
        ]
        for hours, expected in ((8, True), (13, False)):
            old = int((NOW-timedelta(hours=hours)).timestamp()*1000)
            row = observe(pair(pairCreatedAt=old, priceUsd="0.0002"), NOW)
            self.assertEqual(mature_continuation_observation(row, history)["mature_watch"], expected)

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
            {"chain": "solana", "address": "mint", "pair": "pool", "received_at":
             (NOW-timedelta(hours=4, minutes=30)).isoformat(), "price_usd": 0.0001},
            {"chain": "solana", "address": "mint", "pair": "pool", "received_at":
             (NOW-timedelta(minutes=15)).isoformat(), "price_usd": 0.00018},
        ]
        r = trend_observation(row, history)
        self.assertTrue(r["trend_data_sufficient"])
        self.assertTrue(r["trend_watch"])
        self.assertFalse(r["trend_entry_authorized"])

    def test_four_hour_downtrend_rejected(self):
        row = observe(pair(), NOW)
        history = [
            {"chain": "solana", "address": "mint", "pair": "pool", "received_at":
             (NOW-timedelta(hours=4, minutes=30)).isoformat(), "price_usd": 0.0004},
            {"chain": "solana", "address": "mint", "pair": "pool", "received_at":
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
            {"chain": "solana", "address": "mint", "pair": "pool", "received_at":
             (NOW-timedelta(minutes=30)).isoformat(), "price_usd": 0.0002, "volume_5m_usd": 5000},
            {"chain": "solana", "address": "mint", "pair": "pool", "received_at":
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
            {"chain": "solana", "address": "mint", "pair": "pool", "received_at":
             (NOW-timedelta(minutes=30)).isoformat(), "price_usd": 0.0002, "volume_5m_usd": 1000},
            {"chain": "solana", "address": "mint", "pair": "pool", "received_at":
             (NOW-timedelta(minutes=15)).isoformat(), "price_usd": 0.00025, "volume_5m_usd": 2000},
        ]
        self.assertFalse(continuation_observation(row, history)["continuation_watch"])

    def test_mature_continuation_requires_real_history(self):
        old = int((NOW-timedelta(hours=4)).timestamp()*1000)
        row = observe(pair(pairCreatedAt=old, priceUsd="0.0003"), NOW)
        self.assertFalse(mature_continuation_observation(row, [])["mature_watch"])
        history = [
            {"chain":"solana","address":"mint","pair":"pool","received_at":(NOW-timedelta(minutes=45)).isoformat(),"price_usd":0.0002},
            {"chain":"solana","address":"mint","pair":"pool","received_at":(NOW-timedelta(minutes=15)).isoformat(),"price_usd":0.00025},
        ]
        result = mature_continuation_observation(row, history)
        self.assertTrue(result["mature_watch"])
        self.assertFalse(result["mature_entry_authorized"])
        self.assertIn("PAIR_AGE_OUT_OF_RANGE", row["blockers"])

    def test_mature_rejects_overextended_and_illiquid(self):
        old = int((NOW-timedelta(hours=4)).timestamp()*1000)
        history = [
            {"chain":"solana","address":"mint","pair":"pool","received_at":(NOW-timedelta(minutes=45)).isoformat(),"price_usd":0.0002},
            {"chain":"solana","address":"mint","pair":"pool","received_at":(NOW-timedelta(minutes=15)).isoformat(),"price_usd":0.00025},
        ]
        row = observe(pair(pairCreatedAt=old, priceUsd="0.0003",
                           priceChange={"m5":12,"h1":200}), NOW)
        self.assertFalse(mature_continuation_observation(row, history)["mature_watch"])
        row = observe(pair(pairCreatedAt=old, priceUsd="0.0003",
                           liquidity={"usd":1000}), NOW)
        self.assertFalse(mature_continuation_observation(row, history)["mature_watch"])

    def test_dormant_wakeup_requires_real_quiet_history(self):
        row = observe(pair(priceChange={"m5": 8, "h1": 20},
                           volume={"m5": 5000}, txns={"m5": {"buys": 35, "sells": 10}}), NOW)
        history = [
            {"chain": "solana", "address": "mint", "pair": "pool", "received_at":
             (NOW-timedelta(minutes=minutes)).isoformat(),
             "volume_5m_usd": 300, "trades_5m": 4}
            for minutes in (100, 70, 30)
        ]
        self.assertTrue(dormant_wakeup_observation(row, history)["dormant_wakeup_watch"])
        self.assertFalse(dormant_wakeup_observation(row, history)["dormant_entry_authorized"])
        self.assertFalse(dormant_wakeup_observation(row, history[:2])["dormant_wakeup_watch"])
        hot_history = [dict(item, volume_5m_usd=5000) for item in history]
        self.assertFalse(dormant_wakeup_observation(row, hot_history)["dormant_wakeup_watch"])
        illiquid = dict(row, liquidity_usd=1000)
        self.assertFalse(dormant_wakeup_observation(illiquid, history)["dormant_wakeup_watch"])

    def test_revisit_reserves_slots_for_dormant_tokens(self):
        from v13_runner import select_revisits
        quiet = {"chain": "solana", "address": "quiet", "received_at": NOW.isoformat(),
                 "volume_5m_usd": 300, "trades_5m": 2,
                 "liquidity_usd": 25000, "market_cap_usd": 150000,
                 "pair_age_minutes": 500}
        active = dict(quiet, address="active", discovery_alert=True,
                      volume_5m_usd=5000, trades_5m=50)
        keys, dormant_count = select_revisits([quiet, active], NOW)
        self.assertIn(("solana", "quiet"), keys)
        self.assertIn(("solana", "active"), keys)
        self.assertEqual(dormant_count, 1)
        too_old = dict(quiet, received_at=(NOW-timedelta(hours=7)).isoformat())
        keys, count = select_revisits([too_old], NOW)
        self.assertEqual(keys, ())
        self.assertEqual(count, 0)

    def test_discovery_timing_does_not_credit_manual_cases(self):
        from v13_runner import discovery_timing_audit
        old = {"chain":"solana", "address":"mint","pair":"pool", "received_at":
               (NOW-timedelta(minutes=30)).isoformat(),
               "change_1h_pct":180, "source":"search:pump"}
        current = dict(old, received_at=NOW.isoformat(), discovery_alert=True,
                       change_1h_pct=15)
        counts = discovery_timing_audit([current], [old], set())
        self.assertEqual(counts["FIRST_SEEN_ALREADY_OVER_150PCT_1H"], 1)
        self.assertEqual(current["first_observed_1h_pct"], 180)
        self.assertEqual(current["first_alert_at"], NOW.isoformat())
        counts = discovery_timing_audit([current], [old], {("solana","mint")})
        self.assertEqual(counts["MANUAL_CASE_NOT_AUTONOMOUS"], 1)

    def test_public_social_links_are_unverified_metadata(self):
        from v13_runner import public_social_links
        sample = {"info": {"socials": [
            {"type": "twitter", "url": "https://x.com/example"},
            {"type": "telegram", "url": "https://t.me/example"},
            {"type": "twitter", "url": "https://x.com/example"},
            {"type": "twitter", "url": "https://notx.com/impostor"}],
            "websites": [{"url": "https://example.org"}]}}
        links = public_social_links(sample)
        self.assertEqual(len(links), 4)
        self.assertEqual({item["platform"] for item in links},
                         {"x", "telegram", "other"})
        self.assertEqual(public_social_links({"info": {}}), [])

    def test_contrarian_research_is_observational_and_handles_missing_values(self):
        from v13_runner import contrarian_exhaustion_research
        rows = [
            {"chain": "solana", "address": "a", "pair": "p", "change_1h_pct": 175,
             "change_5m_pct": -8, "buy_ratio_5m": 0.32},
            {"chain": "solana", "address": "b", "pair": "p", "change_1h_pct": 180,
             "change_5m_pct": None, "buy_ratio_5m": None},
            {"chain": "solana", "address": "c", "pair": "p", "change_1h_pct": 160,
             "change_5m_pct": 12, "buy_ratio_5m": 0.75},
            {"chain": "solana", "address": "d", "pair": "p", "change_1h_pct": 100,
             "change_5m_pct": -12, "buy_ratio_5m": 0.2},
        ]
        results = contrarian_exhaustion_research(rows)
        self.assertEqual([r["research_status"] for r in results],
                         ["POSSIBLE_EXHAUSTION_UNCONFIRMED",
                          "EXHAUSTION_UNVERIFIED",
                          "EUPHORIA_WITHOUT_EXHAUSTION_CONFIRMATION"])
        self.assertTrue(all(r["trading_signal"] is False for r in results))
        self.assertTrue(all(r["wallet_attribution"] is None for r in results))
        self.assertEqual(contrarian_exhaustion_research([]), [])

    def test_unknown_market_values_never_pass(self):
        r = observe(pair(txns={"m5": {}}, priceChange={}), NOW)
        self.assertFalse(r["market_gates_pass"])
        self.assertFalse(r["entry_authorized"])

if __name__ == "__main__":
    unittest.main()

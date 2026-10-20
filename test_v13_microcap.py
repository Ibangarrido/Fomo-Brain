"""Prospective microcap detector tests, with no network or real trading."""
import unittest
from datetime import datetime, timedelta, timezone
from v13_microcap import microcap_observation

NOW = datetime(2026, 10, 20, 17, 0, tzinfo=timezone.utc)


def row(**kwargs):
    sample = dict(chain="solana", address="mint", pair="pool",
                  received_at=NOW.isoformat(), market_cap_usd=50000,
                  liquidity_usd=8000, pair_age_minutes=90,
                  volume_5m_usd=1800, trades_5m=24, buy_ratio_5m=.75,
                  change_5m_pct=6, change_1h_pct=18)
    sample.update(kwargs)
    return sample


def quiet():
    return [row(received_at=(NOW-timedelta(minutes=m)).isoformat(),
                volume_5m_usd=250, trades_5m=4) for m in (55, 35, 15)]


class MicrocapTests(unittest.TestCase):
    def test_wakeup_requires_observed_quiet_baseline(self):
        result = microcap_observation(row(), quiet())
        self.assertTrue(result["microcap_watch"])
        self.assertFalse(result.get("microcap_entry_authorized", False))
        self.assertTrue(result["microcap_research_only"])

    def test_missing_history_does_not_fabricate_early_signal(self):
        self.assertFalse(microcap_observation(row(), [])["microcap_watch"])
        self.assertFalse(microcap_observation(row(), quiet()[:2])["microcap_watch"])

    def test_rejects_late_momentum_and_illiquidity(self):
        self.assertFalse(microcap_observation(row(change_1h_pct=140), quiet())["microcap_watch"])
        self.assertFalse(microcap_observation(row(liquidity_usd=1000), quiet())["microcap_watch"])
        self.assertFalse(microcap_observation(row(market_cap_usd=250000), quiet())["microcap_watch"])

    def test_does_not_use_future_or_other_pool(self):
        future = row(received_at=(NOW+timedelta(minutes=20)).isoformat(),
                     volume_5m_usd=100, trades_5m=1)
        other = row(pair="other", received_at=(NOW-timedelta(minutes=80)).isoformat(),
                    volume_5m_usd=100, trades_5m=1)
        self.assertFalse(microcap_observation(row(), [future, other])["microcap_watch"])

    def test_no_buy_pressure_no_signal(self):
        self.assertFalse(microcap_observation(row(buy_ratio_5m=.4), quiet())["microcap_watch"])

if __name__ == "__main__":
    unittest.main()

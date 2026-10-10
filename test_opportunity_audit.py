import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import opportunity_audit as audit
from test_fomo_v8 import pair


class OpportunityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.temp.name)
        audit.begin_cycle()
        self.now = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)

    def tearDown(self):
        os.chdir(self.old)
        self.temp.cleanup()

    def observe(self, markets, now=None):
        with contextlib.redirect_stdout(io.StringIO()):
            audit.observe({str(i): p for i, p in enumerate(markets)}, {}, now or self.now)
        return audit.read()["tokens"]

    def test_keeps_baseline_peak_drawdown_and_wallet_reasons(self):
        audit.record_decisions("CONTROL", ["DESCARTE solana:a | cartera sin valoracion completa"])
        audit.record_decisions("VELAS", ["DESCARTE solana:a | ratio compras < 60%"])
        first = self.observe([pair(price=1)])["solana:a"]["first"]
        self.observe([pair(price=3)], self.now + timedelta(hours=1))
        row = self.observe([pair(price=1.5)], self.now + timedelta(hours=2))["solana:a"]
        self.assertEqual(row["first"], first)
        self.assertEqual(row["observed_price_change_pct"], 50)
        self.assertEqual(row["observed_peak_change_pct"], 200)
        self.assertEqual(row["observed_drawdown_from_peak_pct"], -50)
        self.assertEqual(len(first["entry_rejections"]), 2)
        self.assertFalse(first["execution_verified"])
        self.assertNotIn("profit", row)

    def test_market_screens_expose_simultaneous_failures_and_missing_data(self):
        market = pair()
        market["pairCreatedAt"] = int((self.now - timedelta(hours=3)).timestamp() * 1000)
        market["txns"] = {"m5": {"buys": 25, "sells": 25}}
        market["priceChange"] = {"m5": -3}
        row = self.observe([market])["solana:a"]["last"]
        control, extended = row["early_market_screens"]["60"], row["early_market_screens"]["1440"]
        self.assertEqual(control["pair_age_2_60"], "FAIL")
        self.assertEqual(extended["pair_age_2_1440"], "PASS")
        self.assertEqual(extended["buy_count_60pct"], "FAIL")
        self.assertEqual(extended["momentum5m_2_60"], "FAIL")
        self.assertEqual(extended["change1h_max150"], "UNKNOWN")
        self.assertEqual(row["trades5m"], 50)

    def test_missing_invalid_quotes_preserve_last_price_and_report_gaps(self):
        self.observe([pair()])
        bad = pair(price="nan")
        row = self.observe([bad], self.now + timedelta(hours=1))["solana:a"]
        self.assertEqual(row["last"]["price"], 1)
        row = self.observe([pair(price=.5, pool="new")], self.now + timedelta(hours=2))["solana:a"]
        self.assertEqual(row["pair_changes"], 1)
        self.assertEqual(row["max_observation_gap_seconds"], 7200)
        self.assertEqual(row["observed_price_change_pct"], -50)

    def test_manual_winner_is_separate_from_automatic_cohort(self):
        chain, mint = next(iter(audit.MANUAL))
        rows = self.observe([pair(address=mint, liquidity=1), pair(address="loser")])
        self.assertEqual(rows[chain + ":" + mint]["cohort"], "manual_after_event")
        self.assertEqual(rows["solana:loser"]["cohort"], "automatic_prospective")
        self.assertIn((chain, mint), audit.watch_targets(self.now))

    def test_same_contract_different_chains_never_merge_and_liquid_pool_wins(self):
        other = pair(price=7)
        other["chainId"] = "bsc"
        rows = self.observe([pair(price=1, liquidity=20000), pair(price=10, liquidity=10000), other])
        self.assertEqual(rows["solana:a"]["last"]["price"], 1)
        self.assertEqual(rows["bsc:a"]["last"]["price"], 7)

    def test_bound_and_corrupt_state_never_silently_reset(self):
        with patch.object(audit, "LIMIT", 1):
            self.observe([pair(address="a"), pair(address="b")])
        self.assertEqual(len(audit.read()["tokens"]), 1)
        self.assertEqual(audit.read()["capacity_skips"], 1)
        with open(audit.FILE, "w") as handle:
            handle.write("broken")
        with self.assertRaises(json.JSONDecodeError):
            audit.read()

    def test_horizon_freezes_without_claiming_exact_final_quote(self):
        self.observe([pair()])
        row = self.observe([pair(price=2)], self.now + timedelta(hours=73))["solana:a"]
        self.assertTrue(row["complete"])
        self.assertNotIn(("solana", "a"), audit.watch_targets(self.now + timedelta(hours=74)))
        last = row["last"]
        rows = self.observe([pair(price=5)], self.now + timedelta(hours=74))
        self.assertNotIn('solana:a', rows)
        state = audit.read()
        self.assertEqual(state['retired_counts']['horizon_observed'], 1)
        self.assertEqual(set(state['finished_tokens']['solana:a']), {'retired_at', 'reason'})

    def test_completed_case_frees_slot_without_restarting_old_cohort(self):
        with patch.object(audit, 'LIMIT', 1):
            self.observe([pair(address='a')])
            self.observe([pair(address='a', price=2)], self.now + timedelta(hours=73))
            rows = self.observe([pair(address='a', price=7), pair(address='b')],
                                self.now + timedelta(hours=74))
        self.assertEqual(set(rows), {'solana:b'})
        self.assertEqual(audit.read()['retired_counts']['horizon_observed'], 1)
        self.assertNotIn(('solana', 'a'), audit.watch_targets(self.now + timedelta(hours=74)))

    def test_missing_horizon_quote_retires_without_zero_or_final_price(self):
        self.observe([pair(address='a', price=3)])
        self.assertIn('solana:a', self.observe([], self.now + timedelta(hours=95)))
        self.assertNotIn('solana:a', self.observe([], self.now + timedelta(hours=96)))
        state = audit.read()
        self.assertEqual(state['retired_counts']['horizon_unknown'], 1)
        self.assertEqual(state['finished_tokens']['solana:a']['reason'], 'horizon_unknown')
        self.assertNotIn('final_price', state['finished_tokens']['solana:a'])
        self.observe([], self.now + timedelta(hours=97))
        self.assertEqual(audit.read()['retired_counts']['horizon_unknown'], 1)

    def test_manual_case_is_preserved_after_tracking_horizon(self):
        chain, mint = next(iter(audit.MANUAL))
        self.observe([pair(address=mint)])
        rows = self.observe([], self.now + timedelta(hours=100))
        self.assertIn(chain+':'+mint, rows)
        self.assertEqual(audit.read()['finished_tokens'], {})

    def test_corrupt_retirement_summary_does_not_erase_active_cases(self):
        self.observe([pair()])
        state = audit.read()
        state['finished_tokens'] = []
        with open(audit.FILE, 'w') as handle:
            json.dump(state, handle)
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            self.observe([], self.now + timedelta(hours=96))
        self.assertIn('solana:a', audit.read()['tokens'])

    def test_failed_quotes_do_not_starve_other_monitoring_targets(self):
        self.observe([pair(address=str(i)) for i in range(25)])
        first = set(audit.watch_targets(self.now)) - audit.MANUAL
        self.observe([], self.now + timedelta(minutes=1))
        second = set(audit.watch_targets(self.now + timedelta(minutes=1))) - audit.MANUAL
        self.assertEqual(len(first), 10)
        self.assertEqual(len(second), 10)
        self.assertGreater(len(first | second), 10)


if __name__ == "__main__":
    unittest.main()


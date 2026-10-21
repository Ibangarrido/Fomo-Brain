"""Behavior checks: prospective confirmation, accounting and honest missing data."""
import unittest
import json
import tempfile
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import patch
from test_v13_hunter import NOW, pair
from v13_hunter import observe, trend_observation, continuation_observation
from v13_paper import advance, initial_state


def row(price=.0002, address="mint", pool="pool", minutes=0):
    r = observe(pair(priceUsd=str(price)), NOW-timedelta(minutes=minutes))
    r.update(address=address, pair=pool)
    return r


class PaperTests(unittest.TestCase):
    def test_first_observation_does_not_buy(self):
        s, report = advance(initial_state(), [row()], [], NOW)
        self.assertEqual(s["cash_eur"], 100)
        self.assertEqual(report["events"], [])

    def test_confirmed_entry_costs_and_no_duplicate_token(self):
        # Previous snapshot uses an older creation time to remain age-qualified.
        prior = row(.00019, minutes=5)
        s, report = advance(initial_state(), [row(), row(pool="other")], [prior], NOW)
        self.assertEqual(len(s["positions"]), 1)
        self.assertEqual(s["cash_eur"], 90)
        self.assertAlmostEqual(s["positions"][0]["quantity"], 10/(.0002*1.03))
        self.assertAlmostEqual(report["modeled_equity_eur"], 99.4175, places=4)
        self.assertFalse(report["execution_verified"])

    def test_another_pool_future_or_stale_quote_does_not_confirm(self):
        for prior in (row(.00019, pool="other", minutes=5),
                      row(.00019, minutes=-5), row(.00019, minutes=31)):
            prior["market_gates_pass"] = True
            s, _ = advance(initial_state(), [row()], [prior], NOW)
            self.assertEqual(s["positions"], [])

    def test_legacy_gate_flag_cannot_confirm_unknown_volume(self):
        prior = dict(row(.00019, minutes=5), volume_5m_usd=None, market_gates_pass=True)
        s, _ = advance(initial_state(), [row()], [prior], NOW)
        self.assertEqual(s["positions"], [])

    def test_missing_liquidity_does_not_close_or_invent_equity(self):
        s, _ = advance(initial_state(), [row()], [row(.00019, minutes=5)], NOW)
        bad = dict(row(.00001), liquidity_usd=0)
        s, report = advance(s, [bad], [], NOW+timedelta(minutes=15))
        self.assertEqual(len(s["positions"]), 1)
        self.assertEqual(s["cash_eur"], 90)
        self.assertIsNone(report["modeled_equity_eur"])
        self.assertEqual(report["unknown_positions"], 1)

    def test_stop_uses_observed_gap_price_and_cooldown(self):
        s, _ = advance(initial_state(), [row()], [row(.00019, minutes=5)], NOW)
        s, report = advance(s, [row(.0001)], [], NOW+timedelta(minutes=15))
        self.assertEqual(s["positions"], [])
        self.assertEqual(report["events"][0]["reason"], "STOP_OBSERVED")
        self.assertEqual(report["events"][0]["exit_price_usd"], .0001)
        self.assertAlmostEqual(s["cash_eur"], 90+10/1.03*.5*.97)
        newer = NOW+timedelta(minutes=30)
        r = row(.000105); r["received_at"] = newer.isoformat()
        previous = row(.0001); previous["received_at"] = (newer-timedelta(minutes=15)).isoformat()
        s, report = advance(s, [r], [previous], newer)
        self.assertEqual(s["positions"], [])

    def test_closed_audit_separates_price_loss_and_modeled_costs(self):
        state, _ = advance(initial_state(), [row()], [row(.00019, minutes=5)], NOW)
        state, report = advance(state, [row(.00017)], [], NOW+timedelta(minutes=15))
        self.assertEqual(len(report["recent_closed_audit"]), 1)
        audit = report["recent_closed_audit"][0]
        self.assertEqual(audit["reason"], "STOP_OBSERVED")
        self.assertAlmostEqual(audit["gross_price_change_pct"], -15.0)
        self.assertLess(audit["net_modeled_return_pct"], -15)
        self.assertGreater(audit["stop_gap_beyond_10pct_points"], 0)
        self.assertEqual(audit["entry_to_exit_minutes"], 15)

    def test_profit_reserve_and_conservation(self):
        s, _ = advance(initial_state(), [row()], [row(.00019, minutes=5)], NOW)
        s, report = advance(s, [row(.0003)], [], NOW+timedelta(minutes=15))
        pnl = s["closed"][0]["net_pnl_eur"]
        self.assertGreater(pnl, 0)
        self.assertAlmostEqual(s["reserve_eur"], pnl*.5)
        self.assertAlmostEqual(s["cash_eur"]+s["reserve_eur"], 100+pnl)
        self.assertEqual(report["events"][0]["reason"], "TAKE_PROFIT_OBSERVED")

    def test_two_position_cap_and_no_input_mutation(self):
        original = initial_state()
        rows = [row(address=str(i)) for i in range(3)]
        history = [row(.00019, address=str(i), minutes=5) for i in range(3)]
        s, _ = advance(original, rows, history, NOW)
        self.assertEqual(len(s["positions"]), 2)
        self.assertEqual(s["cash_eur"], 80)
        self.assertEqual(original, initial_state())

    def test_invalid_state_and_clock_fail_without_reset(self):
        bad = initial_state(); bad["cash_eur"] = float("nan")
        with self.assertRaises(ValueError):
            advance(bad, [], [], NOW)
        s, _ = advance(initial_state(), [], [], NOW)
        with self.assertRaises(ValueError):
            advance(s, [], [], NOW)

    def test_invalid_price_volume_or_negative_counts_rejected(self):
        for p in (pair(priceUsd="nan"), pair(priceUsd="0"),
                  pair(volume={"m5": 0}), pair(txns={"m5":{"buys":50,"sells":-1}})):
            self.assertFalse(observe(p, NOW)["market_gates_pass"])

    def test_trend_cannot_mix_pool_prices(self):
        history = [dict(row(.0001, pool="other"), received_at=(NOW-timedelta(hours=4)).isoformat()),
                   dict(row(.00018, pool="other"), received_at=(NOW-timedelta(minutes=15)).isoformat())]
        self.assertFalse(trend_observation(row(), history)["trend_data_sufficient"])
        self.assertFalse(continuation_observation(row(), history)["continuation_data_sufficient"])

    def test_runner_restores_ledger_and_follows_open_position(self):
        import v13_runner as runner
        class Clock(datetime):
            current = NOW
            @classmethod
            def now(cls, tz=None):
                return cls.current
        with tempfile.TemporaryDirectory() as folder:
            paths = {"STATE": str(Path(folder)/"history.json"),
                     "OUTPUT": str(Path(folder)/"report.json"),
                     "PAPER_STATE": str(Path(folder)/"ledger.json")}
            sample = pair()
            with patch.multiple(runner, **paths), patch.object(runner, "datetime", Clock), \
                 patch.object(runner, "discover", return_value=([sample], [])) as discover, \
                 patch("builtins.print"):
                runner.main()
                self.assertEqual(json.loads(Path(paths["OUTPUT"]).read_text())["modeled_entries_this_run"], 0)
                Clock.current = NOW+timedelta(minutes=15)
                sample["priceUsd"] = "0.00021"
                runner.main()
                report = json.loads(Path(paths["OUTPUT"]).read_text())
                self.assertEqual(report["modeled_entries_this_run"], 1)
                self.assertEqual(report["paper_portfolio"]["cash_eur"], 90)
                Clock.current = NOW+timedelta(minutes=30)
                runner.main()
                self.assertIn(("solana", "mint"), discover.call_args.args[0])
                self.assertEqual(json.loads(Path(paths["OUTPUT"]).read_text())["modeled_entries_this_run"], 0)
                Path(paths["PAPER_STATE"]).unlink()
                Clock.current = NOW+timedelta(minutes=45)
                with self.assertRaisesRegex(ValueError, "refusing capital reset"):
                    runner.main()


if __name__ == "__main__":
    unittest.main()

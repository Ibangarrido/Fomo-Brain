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
    def test_post_exit_audit_merges_saved_and_history_without_duplicates(self):
        from v13_runner import post_exit_audit
        import json
        end = NOW - timedelta(hours=3)
        trade = {"chain": "solana", "address": "mint", "pair": "pool",
                 "symbol": "TEST", "closed_at": end.isoformat(), "exit_price_usd": 1.0}
        t1 = (end + timedelta(minutes=15)).isoformat()
        t2 = (end + timedelta(minutes=30)).isoformat()
        key = json.dumps([trade[k] for k in ("chain", "address", "pair", "closed_at")])
        stored = {key: {"samples": {t1: 1.1}}}
        history = [
            {"chain": "solana", "address": "mint", "pair": "pool",
             "received_at": t1, "price_usd": 1.1},
            {"chain": "solana", "address": "mint", "pair": "pool",
             "received_at": t2, "price_usd": 1.3},
        ]
        result = post_exit_audit([trade], history, NOW, stored)[0]
        self.assertEqual(result["observations"], 2)
        self.assertEqual(result["max_rebound_from_exit_pct"], 30.0)

    def test_post_exit_audit_survives_pruned_history_and_rejects_future_and_other_pools(self):
        from v13_runner import post_exit_audit
        import json
        end = NOW - timedelta(hours=3)
        trade = {"chain": "solana", "address": "mint", "pair": "pool",
                 "symbol": "TEST", "closed_at": end.isoformat(), "exit_price_usd": 1.0}
        key = json.dumps([trade[k] for k in ("chain", "address", "pair", "closed_at")])
        stored = {key: {"samples": {
            (end + timedelta(minutes=15)).isoformat(): 1.2,
            (NOW + timedelta(minutes=10)).isoformat(): 100.0,
        }}}
        other_pool = {"chain": "solana", "address": "mint", "pair": "other",
                      "received_at": (end + timedelta(minutes=20)).isoformat(), "price_usd": 9.0}
        result = post_exit_audit([trade], [other_pool], NOW, stored)[0]
        self.assertEqual(result["observations"], 1)
        self.assertEqual(result["max_rebound_from_exit_pct"], 20.0)
        self.assertTrue(result["window_complete"])
        self.assertTrue(result["has_observed_post_exit_data"])
        missing = post_exit_audit([trade], [], NOW, {})[0]
        self.assertTrue(missing["window_complete"])
        self.assertFalse(missing["has_observed_post_exit_data"])
        self.assertIsNone(missing["max_rebound_from_exit_pct"])

    def test_first_observation_does_not_buy(self):
        s, report = advance(initial_state(), [row()], [], NOW)
        self.assertEqual(s["cash_eur"], 100)
        self.assertEqual(report["events"], [])

    def test_entry_funnel_records_missing_confirmation_without_trading(self):
        s, report = advance(initial_state(), [row()], [], NOW)
        funnel = report["entry_funnel"]
        self.assertEqual(funnel["observed_pools"], 1)
        self.assertEqual(funnel["market_gate_passes"], 1)
        self.assertEqual(funnel["candidates_evaluated"], 1)
        self.assertEqual(funnel["effective_blocker_counts"],
                         {"AWAITING_SECOND_QUALIFIED_SAME_POOL_OBSERVATION": 1})
        self.assertEqual(s["positions"], [])
        self.assertEqual(s["cash_eur"], 100)

    def test_entry_funnel_counts_failed_confirmation_without_inventing_pnl(self):
        current = row(.00018)
        previous = row(.0002, minutes=5)
        s, report = advance(initial_state(), [current], [previous], NOW)
        self.assertEqual(report["entry_funnel"]["effective_blocker_counts"],
                         {"CONFIRMATION_CHANGE_OUTSIDE_1_12PCT": 1})
        self.assertEqual(report["modeled_equity_eur"], 100)
        self.assertEqual(report["events"], [])

    def test_entry_funnel_empty_when_no_candidate_passes(self):
        bad = dict(row(), market_gates_pass=False, mature_watch=False)
        s, report = advance(initial_state(), [bad], [], NOW)
        self.assertEqual(report["entry_funnel"]["candidates_evaluated"], 0)
        self.assertEqual(report["entry_funnel"]["effective_blocker_counts"], {})
        self.assertEqual(s["cash_eur"], 100)

    def test_confirmed_entry_costs_and_no_duplicate_token(self):
        # Previous snapshot uses an older creation time to remain age-qualified.
        prior = row(.00019, minutes=5)
        s, report = advance(initial_state(), [row(), row(pool="other")], [prior], NOW)
        self.assertEqual(len(s["positions"]), 1)
        self.assertEqual(s["cash_eur"], 90)
        self.assertAlmostEqual(s["positions"][0]["quantity"], 10/(.0002*1.03))
        self.assertAlmostEqual(report["modeled_equity_eur"], 99.4175, places=4)
        self.assertFalse(report["execution_verified"])

    def test_overextended_entry_is_rejected_but_not_removed_from_research(self):
        for changes in ({"change_5m_pct": 20}, {"change_1h_pct": 95}):
            current = row()
            current.update(changes)
            state, report = advance(initial_state(), [current], [row(.00019, minutes=5)], NOW)
            self.assertEqual(state["positions"], [])
            self.assertEqual(report["entry_checks"][0]["blocker"], "ENTRY_OVEREXTENDED_5M_OR_1H")

    def test_entry_stress_test_accounts_for_both_fees(self):
        _, report = advance(initial_state(), [], [], NOW)
        self.assertAlmostEqual(report["entry_stress_test"]["modeled_loss_pct_after_both_fees"], 10.53, places=2)

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

    def test_recent_closed_positions_remain_on_watch_for_two_hours(self):
        from v13_runner import recent_closed_revisits
        trades = [
            {"chain": "solana", "address": "mint", "closed_at": (NOW-timedelta(minutes=30)).isoformat()},
            {"chain": "solana", "address": "mint", "closed_at": (NOW-timedelta(minutes=15)).isoformat()},
            {"chain": "bsc", "address": "old", "closed_at": (NOW-timedelta(minutes=121)).isoformat()},
            {"chain": "bsc", "address": "future", "closed_at": (NOW+timedelta(minutes=1)).isoformat()},
        ]
        self.assertEqual(recent_closed_revisits(trades, NOW), (("solana", "mint"),))

    def test_post_exit_audit_is_observation_only_and_no_future_leak(self):
        from v13_runner import post_exit_audit
        closed = [{"chain": "solana", "address": "mint", "pair": "pool",
                   "symbol": "DTC", "closed_at": NOW.isoformat(), "exit_price_usd": .001}]
        def sample(minutes, price):
            return {"chain": "solana", "address": "mint", "pair": "pool",
                    "received_at": (NOW+timedelta(minutes=minutes)).isoformat(), "price_usd": price}
        history = [sample(15, .0015), sample(90, .0008), sample(130, .01)]
        audit = post_exit_audit(closed, history, NOW+timedelta(minutes=100))[0]
        self.assertFalse(audit["window_complete"])
        self.assertEqual(audit["observations"], 2)
        self.assertEqual(audit["max_rebound_from_exit_pct"], 50)
        self.assertEqual(audit["min_move_from_exit_pct"], -20)
        self.assertTrue(audit["research_only"])

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

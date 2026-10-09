import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from test_fomo_v8 import b, pair
import protection_lab as lab
import copy
from research_metrics import wallet_report, compare


class ResearchMetricsTests(unittest.TestCase):
    def state(self):
        return {"protection_baseline": {"at": "2026-10-01T00:00:00+00:00", "equity": 100},
                "positions": [], "closed": [], "observations": [{
                    "at": "2026-10-02T00:00:00+00:00", "valuation_complete": True,
                    "unverified_quotes": 0, "estimated_equity": 98}]}

    def leg(self, profit, reason="STOP -15%", opened="2026-10-01T01:00:00+00:00"):
        return {"chain": "solana", "address": "mint", "opened_at": opened,
                "closed_at": "2026-10-01T02:00:00+00:00", "profit": profit,
                "exit_reason": reason, "entry_policy_version": "early-r5",
                "entry_risk_policy_version": "capital-r2"}

    def test_partial_and_final_are_one_losing_position_without_mutation(self):
        state = self.state()
        state['closed'] = [self.leg(1, 'PARCIAL +30%'), self.leg(-3)]
        before = copy.deepcopy(state)
        row = wallet_report(state, 'protection_baseline')
        self.assertEqual((row['sale_legs_all_history'], row['new_completed_positions'],
                          row['new_winners'], row['new_losers']), (2, 1, 0, 1))
        self.assertEqual(row['new_completed_realized_profit'], -2)
        self.assertEqual(state, before)

    def test_open_partial_is_not_a_completed_winner(self):
        state = self.state()
        state['closed'] = [self.leg(1, 'PARCIAL +30%')]
        state['positions'] = [dict(state['closed'][0], quote_status='OK')]
        row = wallet_report(state, 'protection_baseline')
        self.assertEqual(row['new_completed_positions'], 0)
        self.assertEqual(row['positions_with_sales_still_open_or_partial_only'], 1)

    def test_inherited_and_changed_policies_are_explicit(self):
        state = self.state()
        state['closed'] = [self.leg(4, opened='2026-09-30T00:00:00+00:00'),
                           dict(self.leg(-2), address='new', entry_risk_policy_version=None),
                           dict(self.leg(1), address='another')]
        row = wallet_report(state, 'protection_baseline')
        self.assertEqual(row['inherited_completed_positions'], 1)
        self.assertEqual(row['inherited_lifetime_realized_profit'], 4)
        self.assertEqual(row['new_completed_positions'], 2)
        self.assertEqual(row['new_completed_realized_profit'], -1)
        self.assertTrue(row['mixed_or_unknown_policies'])

    def test_unknown_mark_or_baseline_cannot_create_advantage(self):
        control, variant = self.state(), self.state()
        variant['positions'] = [dict(self.leg(0), quote_status='NO VERIFICABLE', mark_net=7)]
        self.assertIsNone(compare(control, variant, 'protection_baseline')['relative_equity_advantage'])
        variant = self.state()
        variant['observations'][0].pop('at')
        self.assertIsNone(compare(self.state(), variant, 'protection_baseline')['relative_equity_advantage'])
        variant = self.state()
        for state in (control, variant):
            state['protection_baseline'] = {'at': '2026-10-01T00:00:00+00:00', 'total_equity': None}
        self.assertIsNone(compare(control, variant, 'protection_baseline')['relative_equity_advantage'])

    def test_relative_advantage_is_not_positive_profit_or_winner(self):
        control, variant = self.state(), self.state()
        control['observations'][-1]['estimated_equity'] = 95
        result = compare(control, variant, 'protection_baseline')
        self.assertEqual(result['relative_equity_advantage'], 3)
        self.assertEqual(result['variant']['equity_delta'], -2)
        self.assertFalse(result['winner_selected'])
        self.assertIsNone(result['statistical_significance'])
        variant['protection_baseline']['equity'] = 101
        with self.assertRaises(ValueError):
            compare(control, variant, 'protection_baseline')

    def test_invalid_data_fails_closed(self):
        for mutation in ('profit', 'identity', 'timezone', 'old_observation', 'future_sale'):
            state = self.state()
            state['closed'] = [self.leg(-1)]
            if mutation == 'profit': state['closed'][0]['profit'] = float('nan')
            if mutation == 'identity': state['closed'][0].pop('address')
            if mutation == 'timezone': state['closed'][0]['opened_at'] = '2026-10-01T01:00:00'
            if mutation == 'old_observation': state['observations'][0]['at'] = '2026-09-30T00:00:00+00:00'
            if mutation == 'future_sale': state['closed'][0]['closed_at'] = '2026-10-03T00:00:00+00:00'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                wallet_report(state, 'protection_baseline')


class ProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.temp.name)
        b.REJECTIONS.clear()
        self.token = b.analizar_par(pair())
        for mode in lab.MODES:
            with patch.object(b, "cotizar_posicion", return_value=(1, 20000, pair())), contextlib.redirect_stdout(io.StringIO()):
                b.simular_cartera([self.token], f"fomo_lab_ratio_{mode}_60_r1.json",
                                 confirm=False, entry_mode=mode)
        with contextlib.redirect_stdout(io.StringIO()):
            lab.bootstrap()

    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()

    def read(self, arm="protect", mode="early"):
        with open(lab.filename(mode, arm)) as handle:
            return json.load(handle)

    def step(self, net_pct, arm="protect", mode="early", quote_error=None):
        price = (1 + net_pct/100) * 1.01 * 1.02 / (.99*.98)
        filename = lab.filename(mode, arm)
        kwargs = {"side_effect": quote_error} if quote_error else {"return_value": (price, 20000, pair(price=price))}
        with patch.object(b, "cotizar_posicion", **kwargs), contextlib.redirect_stdout(io.StringIO()):
            b.simular_cartera([], filename, entry_mode=mode, profit_protection=arm=="protect")
        return self.read(arm, mode)

    def test_identical_fork_and_persistence_without_new_funding(self):
        for mode in lab.MODES:
            c, p = self.read("control", mode), self.read("protect", mode)
            for key in ("cash", "reserve", "positions", "closed", "seen", "observations", "risk_control"):
                self.assertEqual(c[key], p[key])
            self.assertEqual(c["protection_baseline"], p["protection_baseline"])
            self.assertEqual(c["cash"], 95)
        before = self.read()
        self.assertFalse(lab.bootstrap())
        self.assertEqual(before, self.read())
        os.remove(lab.filename("early", "protect"))
        with self.assertRaises(ValueError):
            lab.bootstrap()

    def test_retracement_before_arming_does_not_sell(self):
        self.step(11)
        state = self.step(1)
        self.assertEqual(len(state["positions"]), 1)
        self.assertEqual(state["closed"], [])

    def test_protection_arms_and_closes_at_observed_price_with_costs(self):
        state = self.step(12.01)
        self.assertTrue(state["positions"][0]["profit_protection_armed"])
        state = self.step(1.99)
        self.assertEqual(state["positions"], [])
        leg = state["closed"][-1]
        self.assertEqual(leg["exit_reason"], "PROTECCION +12% -> +2%")
        self.assertAlmostEqual(leg["profit"], 5*.0199)
        self.assertAlmostEqual(state["reserve"], leg["profit"]*.5)
        self.assertAlmostEqual(state["cash"]+state["reserve"], 100+leg["profit"])
        self.step(12.01, "control")
        self.assertEqual(len(self.step(1.99, "control")["positions"]), 1)

    def test_gap_below_floor_does_not_fabricate_two_percent_fill(self):
        self.step(13)
        state = self.step(-8)
        leg = state["closed"][-1]
        self.assertEqual(leg["exit_reason"], "PROTECCION +12% -> +2%")
        self.assertAlmostEqual(leg["profit"], -.4)
        self.assertEqual(leg["reserved"], 0)
        self.step(13, mode="impulse")
        state = self.step(-20, mode="impulse")
        self.assertEqual(state["closed"][-1]["exit_reason"], "STOP -15%")

    def test_stale_quote_cannot_arm_or_execute_protection(self):
        state = self.step(20, quote_error=ValueError("sin precio"))
        self.assertFalse(state["positions"][0].get("profit_protection_armed", False))
        self.step(13)
        state = self.step(-8, quote_error=ValueError("sin precio"))
        self.assertEqual(len(state["positions"]), 1)
        self.assertEqual(state["closed"], [])

    def test_old_peak_does_not_arm_and_partial_reserve_still_works(self):
        path = lab.filename("early", "protect")
        state = self.read()
        state["positions"][0]["peak_pnl_net_pct"] = 50
        with open(path, "w") as handle:
            json.dump(state, handle)
        state = self.step(1)
        self.assertFalse(state["positions"][0].get("profit_protection_armed", False))
        state = self.step(31)
        self.assertEqual(state["closed"][-1]["exit_reason"], "PARCIAL +30%")
        self.assertAlmostEqual(state["positions"][0]["budget"], 2.5)
        self.assertAlmostEqual(state["reserve"], state["closed"][-1]["profit"]*.5)

    def test_historical_policy_and_wrong_arm_rejected_before_writes(self):
        with self.assertRaises(ValueError):
            b.simular_cartera([], profit_protection=True)
        path = lab.filename("early", "protect")
        before = self.read()
        with self.assertRaises(ValueError):
            b.simular_cartera([], path, profit_protection=False)
        self.assertEqual(self.read(), before)

    def test_missing_all_books_never_restarts_after_fork(self):
        for mode in lab.MODES:
            for arm in lab.ARMS:
                os.remove(lab.filename(mode, arm))
        with self.assertRaises(ValueError):
            lab.bootstrap()


class VelasProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.temp.name)
        token = b.analizar_par(pair())
        with patch.object(b, "cotizar_posicion", return_value=(1, 20000, pair())), contextlib.redirect_stdout(io.StringIO()):
            b.simular_cartera([token], lab.VELAS_SOURCE, confirm=False)
        with open(lab.VELAS_SOURCE) as handle:
            self.source = json.load(handle)
        with contextlib.redirect_stdout(io.StringIO()):
            lab.bootstrap_velas()

    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()

    def read(self, arm):
        with open(lab.velas_filename(arm)) as handle:
            return json.load(handle)

    def step(self, pct, arm):
        price = (1+pct/100)*1.01*1.02/(.99*.98)
        with patch.object(b, "cotizar_posicion", return_value=(price, 20000, pair(price=price))), contextlib.redirect_stdout(io.StringIO()):
            b.simular_cartera([], lab.velas_filename(arm), profit_protection=arm=="protect")
        return self.read(arm)

    def test_same_funds_and_history_no_restart(self):
        for arm in lab.ARMS:
            state = self.read(arm)
            for key in ("cash", "reserve", "positions", "closed", "seen", "risk_control"):
                expected = self.source[key]
                if key == "positions":
                    expected = [dict(p, protection_fork_at=state["protection_baseline"]["at"]) for p in expected]
                self.assertEqual(state[key], expected)
        self.assertFalse(lab.bootstrap_velas())
        os.remove(lab.velas_filename("protect"))
        with self.assertRaises(ValueError):
            lab.bootstrap_velas()

    def test_bunbara_style_peak_retracement_and_gap(self):
        self.step(12.68, "protect")
        self.step(12.68, "control")
        protected = self.step(1.5, "protect")
        control = self.step(1.5, "control")
        self.assertEqual(protected["closed"][-1]["exit_reason"], "PROTECCION +12% -> +2%")
        self.assertAlmostEqual(protected["closed"][-1]["profit"], .075)
        self.assertEqual(len(control["positions"]), 1)
        control = self.step(-16.63, "control")
        self.assertAlmostEqual(control["closed"][-1]["profit"], -.8315)
        self.assertEqual(control["closed"][-1]["exit_reason"], "STOP -15%")

    def test_same_candle_guard_and_policy_for_both_arms(self):
        from unittest.mock import Mock
        simulator = Mock()
        guards = [Mock(), Mock()]
        with patch("candle_lab.guard", side_effect=guards) as factory, contextlib.redirect_stdout(io.StringIO()):
            lab.run_velas([], simulator)
        self.assertEqual(simulator.call_count, 2)
        for i, call in enumerate(simulator.call_args_list):
            self.assertTrue(call.kwargs["confirm"])
            self.assertEqual(call.kwargs["entry_mode"], "early")
            self.assertEqual(call.kwargs["min_buy_ratio"], .6)
            self.assertIs(call.kwargs["entry_guard"], guards[i])
            self.assertEqual(call.kwargs["profit_protection"], i==1)
            self.assertEqual(factory.call_args_list[i].args[:2], (True, "early"))

    def test_unverified_source_is_not_forked(self):
        for arm in lab.ARMS:
            os.remove(lab.velas_filename(arm))
        os.remove(lab.VELAS_MARKER)
        self.source["observations"][-1]["valuation_complete"] = False
        with open(lab.VELAS_SOURCE, "w") as handle:
            json.dump(self.source, handle)
        with self.assertRaises(ValueError):
            lab.bootstrap_velas()
        self.assertFalse(os.path.exists(lab.velas_filename("control")))


class ComparisonSummaryTests(unittest.TestCase):
    def states(self):
        base = {"at": "2026-10-08T11:00:00+00:00", "equity": 98.0}
        return {arm: {"protection_baseline": dict(base), "closed": [],
                      "observations": [{"estimated_equity": equity,
                                        "valuation_complete": True, "open": 0,
                                        "unverified_quotes": 0}]}
                for arm, equity in (("control", 96.0), ("protect", 97.0))}

    def test_advantage_uses_fork_and_excludes_old_protection_exits(self):
        states = self.states()
        states["protect"]["closed"] = [
            {"closed_at": at, "exit_reason": "PROTECCION +12% -> +2%"}
            for at in ("2026-10-08T10:00:00+00:00", "2026-10-08T12:00:00+00:00")]
        before = json.dumps(states)
        result = lab.comparison_summary(states)
        self.assertEqual(result["control"]["delta"], -2.0)
        self.assertEqual(result["advantage"], 1.0)
        self.assertEqual(result["protect"]["protection_exits"], 1)
        self.assertEqual(json.dumps(states), before)

    def test_unknown_or_nonfinite_equity_cannot_claim_advantage(self):
        for equity, complete in ((None, False), (99.0, False), (float("nan"), True)):
            states = self.states()
            states["protect"]["observations"][0].update(
                estimated_equity=equity, valuation_complete=complete,
                open=1, unverified_quotes=1)
            result = lab.comparison_summary(states)
            self.assertIsNone(result["advantage"])
            self.assertIsNone(result["protect"]["delta"])
            self.assertEqual(result["protect"]["unknown"], 1)

    def test_mismatched_forks_are_rejected(self):
        states = self.states()
        states["protect"]["protection_baseline"]["equity"] = 100.0
        with self.assertRaises(ValueError):
            lab.comparison_summary(states)


if __name__ == "__main__":
    unittest.main()




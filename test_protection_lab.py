import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from test_fomo_v8 import b, pair
import protection_lab as lab


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


if __name__ == "__main__":
    unittest.main()

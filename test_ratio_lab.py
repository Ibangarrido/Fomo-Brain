import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import ratio_lab
from test_fomo_v8 import b, pair


class RatioLabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.temp.name)
        b.REJECTIONS.clear()
        self.fresh_pair = pair(price=1.02)
        self.fresh_pair["txns"]["m5"] = {"buys": 53, "sells": 47}
        self.fresh_pair["volume"]["m5"] = 3600
        self.token = b.analizar_par(self.fresh_pair)
        self.old = dict(self.token, price=1, vol5m=3000,
                        hora=(datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat())

    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()

    def test_threshold_boundaries_in_both_modes(self):
        with patch.object(b, "ultima_lectura_par", return_value=self.old):
            for mode in ("early", "impulse"):
                for ratio, allowed in ((.5199, False), (.52, True), (.5999, True), (.60, True)):
                    token = dict(self.token, buyRatio5m=ratio)
                    self.assertEqual(b.motivo_entrada(token, True, mode, .52) is None, allowed)
                    self.assertEqual(b.motivo_entrada(token, True, mode) is None, ratio >= .60)

    def test_weaker_ratio_does_not_bypass_other_confirmations(self):
        with patch.object(b, "ultima_lectura_par", return_value=self.old):
            self.assertIn("volumen5m", b.motivo_entrada(dict(self.token, vol5m=2900), True, "impulse", .52))
            self.assertIn("precio", b.motivo_entrada(dict(self.token, price=.99), True, "early", .52))
            self.assertIn("liquidez", b.motivo_entrada(dict(self.token, liquidity=18000), True, "early", .52))
        with patch.object(b, "ultima_lectura_par", return_value=None):
            self.assertIn("lectura previa", b.motivo_entrada(self.token, True, "impulse", .52))

    def test_four_new_books_fresh_ratio_costs_and_persistence(self):
        originals = {b.V10_FILE: '{"historic":1}', b.V10_IMPULSE_FILE: '{"historic":2}',
                     "fomo_lab_impulse_control_r1.json": '{"candle":3}'}
        for filename, content in originals.items():
            with open(filename, "w") as f:
                f.write(content)
        # Radar says 70%; the freshly quoted pair has only 53%.
        radar = dict(self.token, buyRatio5m=.70)
        with patch.object(b, "ultima_lectura_par", return_value=self.old), patch.object(b, "cotizar_posicion", return_value=(1.02, 20000, self.fresh_pair)), contextlib.redirect_stdout(io.StringIO()):
            ratio_lab.run([radar], b.simular_cartera)
            ratio_lab.run([radar], b.simular_cartera)
        for mode in ("early", "impulse"):
            for threshold in (60, 52):
                with open(f"fomo_lab_ratio_{mode}_{threshold}_r1.json") as f:
                    state = json.load(f)
                self.assertEqual(len(state["positions"]), int(threshold == 52))
                self.assertEqual(state["cash"], 90 if threshold == 52 else 100)
                self.assertEqual(len(state["observations"]), 2)
                self.assertEqual(state["ratio_experiment"]["min_buy_ratio"], threshold/100)
                self.assertEqual(state["assumptions"]["min_buy_ratio_5m"], threshold/100)
                self.assertIn(f">={threshold}%", state["assumptions"]["entry_policy"])
                if threshold == 52:
                    pos = state["positions"][0]
                    self.assertEqual(pos["entry_snapshot"]["buyRatio5m"], .53)
                    self.assertEqual(pos["entry_min_buy_ratio"], .52)
                    self.assertAlmostEqual(pos["mark_net"], 10*.99*.98/(1.01*1.02))
        for filename, content in originals.items():
            with open(filename) as f:
                self.assertEqual(f.read(), content)

    def test_historical_threshold_and_ratio_book_cannot_be_repurposed(self):
        for filename in (b.V10_FILE, b.V10_IMPULSE_FILE, "fomo_lab_early_velas_r1.json"):
            with self.assertRaises(ValueError):
                b.simular_cartera([], filename, min_buy_ratio=.52)
            self.assertFalse(os.path.exists(filename))
        filename = "fomo_lab_ratio_impulse_52_r1.json"
        with contextlib.redirect_stdout(io.StringIO()):
            b.simular_cartera([], filename, entry_mode="impulse", min_buy_ratio=.52)
        with open(filename) as f:
            before = f.read()
        with self.assertRaises(ValueError):
            b.simular_cartera([], filename, entry_mode="impulse", min_buy_ratio=.60)
        with open(filename) as f:
            self.assertEqual(f.read(), before)

    def test_halted_ratio_book_still_closes_positions(self):
        filename = "fomo_lab_ratio_impulse_52_r1.json"
        with patch.object(b, "ultima_lectura_par", return_value=self.old), patch.object(b, "cotizar_posicion", return_value=(1.02, 20000, self.fresh_pair)), contextlib.redirect_stdout(io.StringIO()):
            b.simular_cartera([self.token], filename, entry_mode="impulse", min_buy_ratio=.52)
        with open(filename) as f:
            state = json.load(f)
        state["risk_control"] = {"halted_at": "test", "halt_reason": "halt"}
        with open(filename, "w") as f:
            json.dump(state, f)
        with patch.object(b, "cotizar_posicion", return_value=(.5, 20000, pair(price=.5))), contextlib.redirect_stdout(io.StringIO()):
            b.simular_cartera([], filename, entry_mode="impulse", min_buy_ratio=.52)
        with open(filename) as f:
            state = json.load(f)
        self.assertEqual(state["positions"], [])
        self.assertEqual(len(state["closed"]), 1)
        self.assertLess(state["closed"][0]["profit"], 0)
        self.assertEqual(state["risk_control"]["halt_reason"], "halt")

    def test_invalid_thresholds_fail_before_writes(self):
        for threshold in (float("nan"), float("inf"), -.1, 1.1):
            with self.assertRaises(ValueError):
                b.simular_cartera([], "fomo_lab_ratio_test.json", min_buy_ratio=threshold)
            with self.assertRaises(ValueError):
                b.motivo_entrada(self.token, min_buy_ratio=threshold)


if __name__ == "__main__":
    unittest.main()

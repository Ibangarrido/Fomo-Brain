import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch, Mock

import volume_lab as lab
from test_fomo_v8 import b, pair


class VolumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.temp.name)
        token = b.analizar_par(pair())
        with patch.object(b, "cotizar_posicion", return_value=(1, 20000, pair())), contextlib.redirect_stdout(io.StringIO()):
            b.simular_cartera([token], lab.SOURCE, confirm=False, entry_mode="impulse")

    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()

    def read(self, path):
        with open(path) as handle:
            return json.load(handle)

    def test_fork_preserves_balances_positions_and_pause(self):
        seed = self.read(lab.SOURCE)
        seed["risk_control"]["pause_until"] = "2099-01-01T00:00:00+00:00"
        with open(lab.SOURCE, "w") as handle:
            json.dump(seed, handle)
        sim = Mock()
        with contextlib.redirect_stdout(io.StringIO()):
            lab.run([], sim)
        sim.assert_not_called()
        control, volume = [self.read(lab.filename(arm)) for arm in lab.ARMS]
        for key in ("cash", "reserve", "positions", "closed", "seen", "risk_control"):
            self.assertEqual(control[key], seed[key])
            self.assertEqual(volume[key], seed[key])
        self.assertEqual(control["volume_baseline"], volume["volume_baseline"])
        self.assertFalse(lab.bootstrap())
        os.remove(lab.filename("volume"))
        with self.assertRaises(ValueError):
            lab.bootstrap()

    def test_invalid_source_does_not_create_accounts(self):
        seed = self.read(lab.SOURCE)
        seed["observations"][-1]["valuation_complete"] = False
        with open(lab.SOURCE, "w") as handle:
            json.dump(seed, handle)
        with self.assertRaises(ValueError):
            lab.bootstrap()
        self.assertFalse(os.path.exists(lab.MARKER))
        self.assertFalse(os.path.exists(lab.filename("control")))

    def test_volume_boundary_and_invalid_values(self):
        for value in (None, "bad", float("nan"), float("inf"), -1, 4999.99):
            self.assertIsNotNone(lab.volume_guard({"vol5m": value}))
        self.assertIsNone(lab.volume_guard({"vol5m": 5000}))

    def test_new_entry_filter_does_not_block_inherited_exit(self):
        with contextlib.redirect_stdout(io.StringIO()):
            lab.bootstrap()
        # Low volume rejects only a new entry; inherited holdings still stop out.
        with patch.object(b, "cotizar_posicion", return_value=(.8, 20000, pair(price=.8))), contextlib.redirect_stdout(io.StringIO()):
            lab.run([], b.simular_cartera)
        for arm in lab.ARMS:
            state = self.read(lab.filename(arm))
            self.assertEqual(state["positions"], [])
            self.assertEqual(state["closed"][-1]["exit_reason"], "STOP -15%")
        new = b.analizar_par(pair(address="new", pool="new-pool"))
        fresh = pair(address="new", pool="new-pool")
        fresh["volume"]["m5"] = 4999
        with patch.object(b, "motivo_entrada", return_value=None), patch.object(b, "cotizar_posicion", return_value=(1, 20000, fresh)), contextlib.redirect_stdout(io.StringIO()):
            lab.run([new], b.simular_cartera)
        self.assertEqual(len(self.read(lab.filename("control"))["positions"]), 1)
        self.assertEqual(self.read(lab.filename("volume"))["positions"], [])


if __name__ == "__main__":
    unittest.main()

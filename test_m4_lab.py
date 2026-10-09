import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import fomo_brain as brain
import m4_lab as lab
from test_fomo_v8 import pair


class M4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = os.getcwd()
        os.chdir(self.temp.name)
        self.seed = {"version": 1, "cash": 82.0, "reserve": 10.0,
                     "positions": [{"chain": "solana", "address": lab.MINT,
                                    "symbol": "M4", "pair": "pool", "quantity": 100,
                                    "budget": 5.0, "mark_net": 6.49,
                                    "quote_status": "NO VERIFICABLE",
                                    "opened_at": "2026-10-06T23:11:00+00:00",
                                    "last_quote_at": "2026-10-06T23:32:00+00:00"}],
                     "closed": [], "seen": ["solana:" + lab.MINT], "observations": []}
        lab.write(lab.SOURCE, self.seed)

    def tearDown(self):
        os.chdir(self.previous)
        self.temp.cleanup()

    def read(self, path):
        with open(path) as handle:
            return json.load(handle)

    def test_fork_preserves_every_balance_position_and_history_once(self):
        original = self.read(lab.SOURCE)
        self.assertTrue(lab.bootstrap())
        self.assertFalse(lab.bootstrap())
        for path in (lab.CONTROL, lab.RECOVERY):
            state = self.read(path)
            for field in ("cash", "reserve", "closed", "seen"):
                self.assertEqual(state[field], original[field])
            self.assertEqual(state["positions"][0]["mark_net"], 6.49)
            self.assertEqual(state["positions"][0]["quantity"], 100)
            self.assertIsNone(state["m4_baseline"]["total_equity"])
        self.assertEqual(self.read(lab.SOURCE), original)
        self.assertTrue(lab.is_quarantined(self.read(lab.RECOVERY)["positions"][0]))
        self.assertFalse(lab.is_quarantined(self.read(lab.CONTROL)["positions"][0]))

    def test_missing_arm_never_resets_capital(self):
        lab.bootstrap()
        os.remove(lab.RECOVERY)
        with self.assertRaises(ValueError):
            lab.bootstrap()

    def test_unknown_zero_for_risk_does_not_become_a_sale(self):
        state = copy.deepcopy(self.seed)
        state["cash"] = 60
        reason = brain.freno_cartera_v10(state, datetime.now(timezone.utc), conservative_unknown=True)
        self.assertIn("70.00", reason)
        self.assertEqual(state["positions"], self.seed["positions"])
        self.assertEqual(state["closed"], [])

    def test_quarantine_cannot_be_enabled_on_original_wallet(self):
        with self.assertRaises(ValueError):
            brain.simular_cartera([], lab.SOURCE, quarantine_m4=True)

    def test_recovery_buys_from_existing_cash_control_stays_paused(self):
        lab.bootstrap()
        market = pair(address="new-token", pool="new-pool")
        token = brain.analizar_par(market)
        previous = dict(token, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                        price=.95, vol5m=3000)
        def quote(position):
            if position["address"] == lab.MINT:
                raise ValueError("M4 unavailable")
            return 1, 20000, market
        for path, recovery in ((lab.CONTROL, False), (lab.RECOVERY, True)):
            with patch.object(brain, "cotizar_posicion", side_effect=quote), \
                    patch.object(brain, "cargar_memoria", return_value=[previous]), \
                    contextlib.redirect_stdout(io.StringIO()):
                brain.simular_cartera([token], path, confirm=True, quarantine_m4=recovery)
        control, recovery = self.read(lab.CONTROL), self.read(lab.RECOVERY)
        self.assertEqual(control["cash"], 82)
        self.assertEqual(len(control["positions"]), 1)
        self.assertEqual(recovery["cash"], 77)
        self.assertEqual(recovery["reserve"], 10)
        self.assertEqual(len(recovery["positions"]), 2)
        self.assertEqual(recovery["positions"][0]["mark_net"], 6.49)
        self.assertEqual(recovery["closed"], [])
        self.assertIsNone(recovery["observations"][-1]["estimated_equity"])

    def test_only_inherited_exact_contract_bypasses_pause_and_net_stays_unknown(self):
        lab.bootstrap()
        for path, recovery in ((lab.CONTROL, False), (lab.RECOVERY, True)):
            with patch.object(brain, "cotizar_posicion", side_effect=ValueError("No quote")), \
                    contextlib.redirect_stdout(io.StringIO()):
                brain.simular_cartera([], path, quarantine_m4=recovery)
            state = self.read(path)
            self.assertEqual(state["cash"], 82)
            self.assertEqual(state["reserve"], 10)
            self.assertEqual(len(state["positions"]), 1)
            self.assertEqual(state["closed"], [])
            self.assertIsNone(state["observations"][-1]["estimated_equity"])
            self.assertFalse(state["observations"][-1]["valuation_complete"])
            paused = any("ENTRADAS PAUSADAS" in note for note in state["last_run_notes"])
            self.assertEqual(paused, not recovery)
        state = self.read(lab.RECOVERY)
        unknown = dict(state["positions"][0], address="another-token")
        state["positions"].append(unknown)
        lab.write(lab.RECOVERY, state)
        with patch.object(brain, "cotizar_posicion", side_effect=ValueError("No quote")), \
                contextlib.redirect_stdout(io.StringIO()):
            brain.simular_cartera([], lab.RECOVERY, quarantine_m4=True)
        self.assertTrue(any("ENTRADAS PAUSADAS" in note
                            for note in self.read(lab.RECOVERY)["last_run_notes"]))


if __name__ == "__main__":
    unittest.main()

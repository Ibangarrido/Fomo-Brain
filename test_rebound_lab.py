import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import fomo_brain as brain
import rebound_lab as lab
import m4_lab
from test_fomo_v8 import pair


class ReboundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.temp.name)
        self.seed = {"version": 1, "cash": 82., "reserve": 10., "positions": [
            {"chain": "solana", "address": m4_lab.MINT, "pair": "old", "symbol": "M4",
             "quantity": 100, "budget": 5., "mark_net": 6.49, "m4_quarantine": True,
             "quote_status": "NO VERIFICABLE", "last_quote_at": "2026-10-06T23:32:00+00:00",
             "opened_at": "2026-10-06T23:11:00+00:00"}], "closed": [], "seen": ["solana:" + m4_lab.MINT],
             "observations": [], "m4_experiment": {"version": "m4-r1", "arm": "recovery"}}
        m4_lab.write(lab.SOURCE, self.seed)

    def tearDown(self):
        os.chdir(self.old)
        self.temp.cleanup()

    def read(self, path):
        with open(path) as handle:
            return json.load(handle)

    def test_fork_preserves_balances_history_once_and_missing_arm_refuses_reset(self):
        self.assertTrue(lab.bootstrap())
        self.assertFalse(lab.bootstrap())
        for path in (lab.CONTROL, lab.EXTENDED):
            state = self.read(path)
            for k in self.seed:
                self.assertEqual(state[k], self.seed[k])
        self.assertEqual(self.read(lab.SOURCE), self.seed)
        os.remove(lab.CONTROL)
        with self.assertRaises(ValueError):
            lab.bootstrap()

    def token_and_previous(self, age=900):
        p = pair(address="rebound", pool="new", price=1, liquidity=25000)
        token = brain.analizar_par(p)
        token["ageMinutes"] = age
        previous = dict(token, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(), price=.95)
        return p, token, previous

    def test_older_token_only_bypasses_age_and_keeps_other_gates(self):
        _, token, old = self.token_and_previous()
        with patch.object(brain, "cargar_memoria", return_value=[old]):
            self.assertIn("edad", brain.motivo_entrada(token, True))
            self.assertIsNone(brain.motivo_entrada(token, True, max_pair_age_minutes=1440))
            for field, value in (("buyRatio5m", .59), ("liquidity", 19000), ("change1h", 151),
                                 ("change5m", -2), ("ageMinutes", 1441), ("ageMinutes", None)):
                self.assertIsNotNone(brain.motivo_entrada(dict(token, **{field: value}), True, max_pair_age_minutes=1440))
        with patch.object(brain, "cargar_memoria", return_value=[]):
            self.assertIsNotNone(brain.motivo_entrada(token, True, max_pair_age_minutes=1440))

    def test_extended_buy_uses_existing_cash_and_keeps_unknown_equity(self):
        lab.bootstrap()
        p, token, old = self.token_and_previous()
        p["pairCreatedAt"] = int((datetime.now(timezone.utc)-timedelta(minutes=900)).timestamp()*1000)
        def quote(position):
            if position["address"] == m4_lab.MINT:
                raise ValueError("M4 unknown")
            return 1, 25000, p
        with patch.object(brain, "cotizar_posicion", side_effect=quote), \
                patch.object(brain, "cargar_memoria", return_value=[old]), \
                patch.dict(os.environ, {"BRAIN_QUOTE_GUARD": "0"}), contextlib.redirect_stdout(io.StringIO()):
            for path, ceiling in ((lab.CONTROL, 60), (lab.EXTENDED, 1440)):
                brain.simular_cartera([token], path, confirm=True, quarantine_m4=True, max_pair_age_minutes=ceiling)
        control, extended = self.read(lab.CONTROL), self.read(lab.EXTENDED)
        self.assertEqual(control["cash"], 82)
        self.assertEqual(extended["cash"], 77)
        self.assertEqual(extended["reserve"], 10)
        self.assertEqual(len(extended["positions"]), 2)
        self.assertEqual(extended["positions"][0]["mark_net"], 6.49)
        self.assertIsNone(extended["observations"][-1]["estimated_equity"])
        self.assertEqual(extended["positions"][1]["entry_max_pair_age_minutes"], 1440)

    def test_cannot_widen_original_wallet_or_create_unforked_wallet(self):
        with self.assertRaises(ValueError):
            brain.simular_cartera([], lab.SOURCE, max_pair_age_minutes=1440)
        with self.assertRaises(ValueError):
            brain.simular_cartera([], lab.EXTENDED, quarantine_m4=True, max_pair_age_minutes=1440)
        self.assertFalse(os.path.exists(lab.EXTENDED))

    def test_capital_brake_not_reset_or_bypassed(self):
        self.seed["cash"] = 65
        m4_lab.write(lab.SOURCE, self.seed)
        with self.assertRaises(ValueError):
            lab.bootstrap()
        self.assertFalse(os.path.exists(lab.EXTENDED))
        state = copy.deepcopy(self.seed)
        self.assertIsNotNone(brain.freno_cartera_v10(state, datetime.now(timezone.utc), conservative_unknown=True))
        self.assertEqual(state["positions"], self.seed["positions"])


if __name__ == "__main__":
    unittest.main()

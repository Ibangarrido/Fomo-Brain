import copy
import contextlib
import io
import json
import tempfile
from datetime import timedelta

import continuation_lab as lab
from test_fomo_v8 import pair
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import fomo_brain as brain


class ContinuationPinTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        self.path = "fomo_lab_continuation_control_r1.json"
        self.legacy = {"chain": "solana", "address": "CJYxdC79qMe94db5cS6wMh7oi5Fsy3BJQMH2KxVB3my3",
                       "opened_at": "2026-10-01T00:00:00+00:00",
                       "quote_status": "UNKNOWN", "quantity": 7}
        self.state = {"cash": 98.58, "reserve": 1.08,
                      "closed": [{"profit": 2.17}], "positions": [self.legacy.copy()]}

    def isolate(self, state, pin):
        with patch.dict(os.environ, {"BRAIN_UNKNOWN_ISOLATION": "1",
                                      "BRAIN_CONTROL_LEGACY_ADDRESS": pin}):
            return brain.isolate_existing_unknowns(state, self.path, self.now)

    def test_exact_pin_preserves_accounting_and_epoch(self):
        before = copy.deepcopy(self.state)
        keys = self.isolate(self.state, self.legacy["address"])
        self.assertEqual(len(keys), 1)
        for field in ("cash", "reserve", "closed", "positions"):
            self.assertEqual(self.state[field], before[field])
        epoch = copy.deepcopy(self.state["unknown_isolation_epoch"])
        self.assertEqual(self.isolate(self.state, self.legacy["address"]), keys)
        self.assertEqual(self.state["unknown_isolation_epoch"], epoch)
        self.state["positions"].append(dict(self.legacy, address="new_unknown"))
        self.assertEqual(self.isolate(self.state, self.legacy["address"]), keys)
        self.assertNotIn(("solana", "new_unknown", self.legacy["opened_at"]), keys)

    def test_missing_or_wrong_pin_never_isolates(self):
        for pin in ("", "wrong"):
            state = copy.deepcopy(self.state)
            self.assertEqual(self.isolate(state, pin), set())
            self.assertNotIn("unknown_isolation_epoch", state)

    def test_two_unknown_positions_never_initialize_epoch(self):
        state = copy.deepcopy(self.state)
        state["positions"].append(dict(self.legacy, address="new_unknown"))
        self.assertEqual(self.isolate(state, self.legacy["address"]), set())
        self.assertNotIn("unknown_isolation_epoch", state)

    def test_other_wallet_never_inherits_continuation_pin(self):
        with patch.dict(os.environ, {"BRAIN_UNKNOWN_ISOLATION": "1",
                                      "BRAIN_CONTROL_LEGACY_ADDRESS": self.legacy["address"]}):
            self.assertEqual(brain.isolate_existing_unknowns(
                self.state, "fomo_lab_continuation_50_r1.json", self.now), set())
        self.assertNotIn("unknown_isolation_epoch", self.state)

    def test_isolated_legacy_does_not_consume_paper_slot(self):
        keys = self.isolate(self.state, self.legacy["address"])
        self.assertEqual(brain.active_paper_slots(self.state["positions"], keys), 0)
        self.state["positions"].append(dict(self.legacy, address="new_unknown"))
        self.assertEqual(brain.active_paper_slots(self.state["positions"], keys), 1)
        self.assertEqual(brain.active_paper_slots(self.state["positions"], set()), 2)

    def test_three_new_positions_exhaust_capacity(self):
        keys = self.isolate(self.state, self.legacy["address"])
        for i in range(3):
            self.state["positions"].append(dict(self.legacy, address=f"new_{i}", quote_status="OK"))
        self.assertEqual(brain.active_paper_slots(self.state["positions"], keys), 3)
        self.assertEqual(self.state["cash"], 98.58)
        self.assertEqual(self.state["reserve"], 1.08)
        self.assertEqual(len(self.state["closed"]), 1)

    def test_full_paper_entry_with_legacy_unknown_keeps_ledger(self):
        """Offline integration: real simulator decision, mocked market, no trading."""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                lab.bootstrap()
                path = lab.ARMS["control"][0]
                raw = pair(address="control_fixture", pool="control_pair",
                           liquidity=25000, price=1)
                raw["_brain_received_at"] = datetime.now(timezone.utc).isoformat()
                token = brain.analizar_par(raw)
                self.assertIsNotNone(token)
                old = dict(token, price=.98, received_at=(datetime.now(timezone.utc) -
                           timedelta(seconds=60)).isoformat())
                with open(path) as f:
                    state = json.load(f)
                legacy = dict(self.legacy, symbol="Coin", pair="legacy_pair",
                              budget=5, entry_price=1, last_quote_at=old["received_at"])
                state.update(cash=98.58, reserve=1.08,
                             positions=[legacy],
                             closed=[{"profit": .70}, {"profit": .70}, {"profit": .77}],
                             recovery_pending_signals={
                                 token["chain"] + ":" + token["address"]: old})
                with open(path, "w") as f:
                    json.dump(state, f)
                def offline_quote(pos):
                    if pos["address"] == legacy["address"]:
                        raise ValueError("Sin par verificable del mismo contrato y cadena")
                    return (1, 25000, raw)
                with (patch.dict(os.environ, {
                          "BRAIN_UNKNOWN_ISOLATION": "1",
                          "BRAIN_CONTROL_LEGACY_ADDRESS": legacy["address"],
                          "BRAIN_QUOTE_GUARD": "0"}),
                      patch.object(brain, "cotizar_posicion", side_effect=offline_quote),
                      patch.object(brain, "pedir_json",
                                   side_effect=AssertionError("No network allowed")),
                      contextlib.redirect_stdout(io.StringIO())):
                    brain.simular_cartera([token], path, entry_mode="early",
                                         min_buy_ratio=.75)
                with open(path) as f:
                    after = json.load(f)
                self.assertEqual(len(after["positions"]), 2)
                self.assertEqual(after["positions"][0]["address"], legacy["address"])
                self.assertEqual(after["positions"][0]["quote_status"], "NO VERIFICABLE")
                self.assertEqual(after["positions"][1]["address"], token["address"])
                self.assertEqual(after["cash"], 93.58)
                self.assertEqual(after["reserve"], 1.08)
                self.assertEqual(after["closed"], state["closed"])
                self.assertEqual(after["last_entry_audit"]["entered"], 1)
                self.assertIsNone(after["observations"][-1]["estimated_equity"])
                self.assertEqual(len(after["unknown_isolation_epoch"]["positions"]), 1)
            finally:
                os.chdir(cwd)

    def test_epoch_drift_fails_closed(self):
        self.isolate(self.state, self.legacy["address"])
        self.assertEqual(self.isolate(self.state, "different"), set())
        self.assertEqual(self.isolate(self.state, ""), set())


if __name__ == "__main__":
    unittest.main()

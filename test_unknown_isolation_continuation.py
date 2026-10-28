"""Regression checks for explicit, one-time PAPER unknown-position isolation."""
import contextlib
import io
import json
import tempfile
from datetime import timedelta
import continuation_lab as lab
from test_fomo_v8 import pair
import fomo_brain as brain
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from fomo_brain import isolate_existing_unknowns, active_position_slots


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.old = {"chain": "solana", "address": "legacy", "opened_at": "old", "quote_status": "NO VERIFICABLE"}
        self.state = {"positions": [dict(self.old)], "cash": 93.0, "reserve": 2.0, "closed": [{"id": "historic"}]}

    def test_both_requested_wallets_keep_accounting(self):
        for path in ("fomo_lab_continuation_control_r1.json", "fomo_lab_pattern_pullback_r1.json"):
            with self.subTest(path=path), patch.dict(os.environ, {"BRAIN_UNKNOWN_ISOLATION": "1", "BRAIN_CONTROL_LEGACY_ADDRESS": "legacy", "BRAIN_PATTERN_LEGACY_ADDRESS": "legacy"}):
                state = {"positions": [dict(self.old)], "cash": 93.0, "reserve": 2.0, "closed": [{"id": "historic"}]}
                keys = isolate_existing_unknowns(state, path, datetime.now(timezone.utc))
                self.assertIn(("solana", "legacy", "old"), keys)
                self.assertEqual(state["cash"], 93.0)
                self.assertEqual(state["reserve"], 2.0)
                self.assertEqual(len(state["closed"]), 1)
                self.assertEqual(len(state["positions"]), 1)
                state["positions"].append({"chain": "solana", "address": "new", "opened_at": "later", "quote_status": "NO VERIFICABLE"})
                self.assertNotIn(("solana", "new", "later"), isolate_existing_unknowns(state, path, datetime.now(timezone.utc)))

    def test_slots_are_released_only_for_still_unknown_legacy(self):
        legacy = dict(self.old)
        fresh = {"chain": "solana", "address": "fresh", "opened_at": "new", "quote_status": "OK"}
        key = ("solana", "legacy", "old")
        self.assertEqual(active_position_slots([legacy, fresh], {key}), 1)
        self.assertEqual(active_position_slots([legacy, fresh], set()), 2)
        legacy["quote_status"] = "OK"
        self.assertEqual(active_position_slots([legacy, fresh], {key}), 2)

    def test_new_unknown_remains_a_blocking_slot(self):
        with patch.dict(os.environ, {"BRAIN_UNKNOWN_ISOLATION": "1", "BRAIN_CONTROL_LEGACY_ADDRESS": "legacy", "BRAIN_PATTERN_LEGACY_ADDRESS": "legacy"}):
            now = datetime.now(timezone.utc)
            keys = isolate_existing_unknowns(self.state, "fomo_lab_pattern_pullback_r1.json", now)
            self.state["positions"].append({"chain": "solana", "address": "new", "opened_at": "new", "quote_status": "NO VERIFICABLE"})
            self.assertEqual(active_position_slots(self.state["positions"], keys), 1)

    def test_wrong_or_missing_pin_fails_closed(self):
        path = "fomo_lab_continuation_control_r1.json"
        for pin in ("", "different"):
            state = {"positions": [dict(self.old)], "cash": 93.0, "reserve": 2.0, "closed": []}
            with patch.dict(os.environ, {"BRAIN_UNKNOWN_ISOLATION": "1", "BRAIN_CONTROL_LEGACY_ADDRESS": pin}):
                self.assertEqual(isolate_existing_unknowns(state, path, datetime.now(timezone.utc)), set())
                self.assertNotIn("unknown_isolation_epoch", state)

    def test_multiple_unknowns_cannot_start_epoch(self):
        state = {"positions": [dict(self.old), dict(self.old, address="new")], "cash": 93.0, "reserve": 2.0, "closed": []}
        with patch.dict(os.environ, {"BRAIN_UNKNOWN_ISOLATION": "1", "BRAIN_CONTROL_LEGACY_ADDRESS": "legacy"}):
            self.assertEqual(isolate_existing_unknowns(state, "fomo_lab_continuation_control_r1.json", datetime.now(timezone.utc)), set())
            self.assertNotIn("unknown_isolation_epoch", state)

    def test_pin_change_after_epoch_cannot_relabel_position(self):
        path = "fomo_lab_pattern_pullback_r1.json"
        with patch.dict(os.environ, {"BRAIN_UNKNOWN_ISOLATION": "1", "BRAIN_PATTERN_LEGACY_ADDRESS": "legacy"}):
            self.assertEqual(len(isolate_existing_unknowns(self.state, path, datetime.now(timezone.utc))), 1)
        with patch.dict(os.environ, {"BRAIN_UNKNOWN_ISOLATION": "1", "BRAIN_PATTERN_LEGACY_ADDRESS": "new"}):
            self.assertEqual(isolate_existing_unknowns(self.state, path, datetime.now(timezone.utc)), set())

    def test_full_paper_entry_with_legacy_unknown_keeps_ledger(self):
        """Offline integration: real simulator decision, mocked market, no trading."""
        for arm in ("control", "pattern_pullback"):
            with self.subTest(arm=arm):
            with tempfile.TemporaryDirectory() as tmp:
                cwd = os.getcwd()
                try:
                    os.chdir(tmp)
                    lab.bootstrap()
                    lab.bootstrap_pattern()
                    path = lab.ARMS[arm][0]
                    raw = pair(address="control_fixture", pool="control_pair",
                               liquidity=25000, price=1)
                    raw["_brain_received_at"] = datetime.now(timezone.utc).isoformat()
                    token = brain.analizar_par(raw)
                    self.assertIsNotNone(token)
                    old = dict(token, price=.98, received_at=(datetime.now(timezone.utc) -
                               timedelta(seconds=60)).isoformat())
                    with open(path) as f:
                        state = json.load(f)
                    legacy = dict({"chain": "solana", "address": "CJYxdC79qMe94db5cS6wMh7oi5Fsy3BJQMH2KxVB3my3", "opened_at": "2026-10-01T00:00:00+00:00", "quote_status": "UNKNOWN", "quantity": 7}, symbol="Coin", pair="legacy_pair",
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
                              "BRAIN_PATTERN_LEGACY_ADDRESS": legacy["address"],
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

    def test_opt_in_only(self):
        with patch.dict(os.environ, {"BRAIN_UNKNOWN_ISOLATION": "0"}):
            self.assertFalse(isolate_existing_unknowns(self.state, "fomo_lab_continuation_control_r1.json", datetime.now(timezone.utc)))
            self.assertNotIn("unknown_isolation_epoch", self.state)


if __name__ == "__main__":
    unittest.main()

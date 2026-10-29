"""Offline regression for the independent M4 fresh PAPER wrapper."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import m4_fresh_lab as fresh

class FreshM4Tests(unittest.TestCase):
    def test_disabled_does_not_simulate(self):
        with patch.dict(os.environ, BRAIN_M4_FRESH_LAB="0"):
            fresh.run([], lambda *a, **k: self.fail("should be disabled"))

    def test_separate_file_and_no_legacy_transfer(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, fresh.FILE)
            def fake_simulate(ranking, filename, label, **kwargs):
                self.assertEqual(filename, fresh.FILE)
                self.assertEqual(kwargs, {"confirm": True, "entry_mode": "early", "min_buy_ratio": .60})
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"cash": 100., "reserve": 0., "positions": [], "closed": []}, f)
            old = os.getcwd()
            try:
                os.chdir(d)
                with patch.dict(os.environ, BRAIN_M4_FRESH_LAB="1"):
                    fresh.run([], fake_simulate)
            finally:
                os.chdir(old)
            self.assertTrue(os.path.isfile(path))


class MaccaIsolationTests(unittest.TestCase):
    def test_exact_reviewed_position_only_and_accounting_preserved(self):
        import copy
        from datetime import datetime, timezone
        from fomo_brain import isolate_existing_unknowns, active_position_slots
        legacy = {"chain": "solana",
                  "address": "61uUYv7jRhZkpNuG6DCFppsSaFBea5TP7fLuRzQ4pump",
                  "opened_at": "2026-10-27T15:45:34.315088+00:00",
                  "quote_status": "NO VERIFICABLE", "quantity": 45022.50945382653}
        state = {"positions": [legacy], "cash": 95.55322510192195,
                 "reserve": .5532251019219565, "closed": [{"profit": 1.10645}]}
        before = copy.deepcopy(state)
        with patch.dict(os.environ, BRAIN_UNKNOWN_ISOLATION="1",
                        BRAIN_M4_FRESH_LEGACY_ADDRESS=legacy["address"]):
            now = datetime.now(timezone.utc)
            keys = isolate_existing_unknowns(state, fresh.FILE, now)
            self.assertEqual(len(keys), 1)
            self.assertEqual(active_position_slots(state["positions"], keys), 0)
            self.assertEqual({k: state[k] for k in before}, before)
            # A later unquoted position remains outside the isolation epoch.
            later = dict(legacy, opened_at="2026-10-29T00:00:00+00:00")
            state["positions"].append(later)
            self.assertEqual(isolate_existing_unknowns(state, fresh.FILE, now), keys)
            self.assertEqual(active_position_slots(state["positions"], keys), 1)
            # A new epoch cannot hide a re-entry in the same contract.
            wrong = dict(before, positions=[later])
            self.assertEqual(isolate_existing_unknowns(wrong, fresh.FILE, now), set())

    def test_unset_pin_does_not_isolate(self):
        from datetime import datetime, timezone
        from fomo_brain import isolate_existing_unknowns
        with patch.dict(os.environ, BRAIN_UNKNOWN_ISOLATION="1",
                        BRAIN_M4_FRESH_LEGACY_ADDRESS=""):
            self.assertEqual(isolate_existing_unknowns(
                {"positions": []}, fresh.FILE, datetime.now(timezone.utc)), set())

    def test_macca_does_not_block_guarded_paper_entry(self):
        import contextlib
        import io
        from datetime import datetime, timezone, timedelta
        import fomo_brain as brain
        from test_fomo_v8 import pair
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, fresh.FILE)
            now = datetime.now(timezone.utc)
            raw = pair(address="m4_candidate", pool="candidate_pool", liquidity=25000, price=1)
            raw["_brain_received_at"] = now.isoformat()
            token = brain.analizar_par(raw)
            old = dict(token, price=.98, received_at=(now-timedelta(seconds=60)).isoformat(),
                       hora=(now-timedelta(seconds=60)).isoformat())
            legacy = {"chain": "solana",
                      "address": "61uUYv7jRhZkpNuG6DCFppsSaFBea5TP7fLuRzQ4pump",
                      "opened_at": "2026-10-27T15:45:34.315088+00:00",
                      "quote_status": "NO VERIFICABLE", "quantity": 45022.50945382653,
                      "symbol": "MACCA", "pair": "legacy_pool", "budget": 5,
                      "entry_price": .0001078, "last_quote_at": now.isoformat()}
            state = {"version": 1, "started_at": now.isoformat(), "cash": 95.55322510192195,
                     "reserve": .5532251019219565, "positions": [legacy],
                     "closed": [], "seen": ["solana:"+legacy["address"]], "observations": []}
            with open(path, "w") as f:
                json.dump(state, f)
            def quote(pos):
                if pos["address"] == legacy["address"]:
                    raise ValueError("Liquidez insuficiente; salida no verificable")
                return 1, 25000, raw
            with (patch.dict(os.environ, BRAIN_UNKNOWN_ISOLATION="1",
                             BRAIN_M4_FRESH_LEGACY_ADDRESS=legacy["address"], BRAIN_QUOTE_GUARD="1"),
                  patch.object(brain, "cotizar_posicion", side_effect=quote),
                  patch.object(brain, "ultima_lectura_par", return_value=old),
                  patch("quote_safety.entry_fees", return_value=({"status": "VERIFICADO"}, None)) as fees,
                  patch.object(brain, "pedir_json", side_effect=AssertionError("No network")),
                  contextlib.redirect_stdout(io.StringIO())):
                brain.simular_cartera([token], path, confirm=True)
            with open(path) as f:
                after = json.load(f)
            self.assertEqual(after["last_entry_audit"]["entered"], 1, after["last_run_notes"])
            fees.assert_called_once()
            self.assertEqual(after["positions"][0]["quantity"], legacy["quantity"])
            self.assertEqual(after["positions"][0]["quote_status"], "NO VERIFICABLE")
            self.assertAlmostEqual(after["cash"], state["cash"]-5)
            self.assertEqual(after["reserve"], state["reserve"])
            self.assertEqual(after["closed"], [])
            obs = after["observations"][-1]
            self.assertFalse(obs["valuation_complete"])
            self.assertIsNone(obs["estimated_equity"])
            self.assertFalse(obs["unknown_valuation_blocks_entries"])
            self.assertEqual(obs["free_entry_slots"], 2)
            self.assertIsNotNone(after["positions"][1]["entry_final_quote"])

if __name__ == "__main__":
    unittest.main()

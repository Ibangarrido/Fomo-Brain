"""Regression checks for explicit, one-time PAPER unknown-position isolation."""
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

    def test_opt_in_only(self):
        with patch.dict(os.environ, {"BRAIN_UNKNOWN_ISOLATION": "0"}):
            self.assertFalse(isolate_existing_unknowns(self.state, "fomo_lab_continuation_control_r1.json", datetime.now(timezone.utc)))
            self.assertNotIn("unknown_isolation_epoch", self.state)


if __name__ == "__main__":
    unittest.main()

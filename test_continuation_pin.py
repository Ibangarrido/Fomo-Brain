import copy
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import fomo_brain as brain


class ContinuationPinTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        self.path = "fomo_lab_continuation_control_r1.json"
        self.legacy = {"chain": "solana", "address": "CJYxdC79legacy",
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

    def test_epoch_drift_fails_closed(self):
        self.isolate(self.state, self.legacy["address"])
        self.assertEqual(self.isolate(self.state, "different"), set())
        self.assertEqual(self.isolate(self.state, ""), set())


if __name__ == "__main__":
    unittest.main()

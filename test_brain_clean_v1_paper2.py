import copy
import tempfile
import unittest
from pathlib import Path

import brain_clean_v1 as brain
import brain_clean_v1_paper2 as paper2


class SecondPaperLedgerTests(unittest.TestCase):
    def test_independent_baseline_and_no_cross_portfolio_mutation(self):
        original = brain.new_state()
        original["cash"] = 33.9529
        original["positions"]["old:pool"] = {"key": "old:pool", "cost": 10}
        frozen = copy.deepcopy(original)
        second = paper2.seed()
        self.assertEqual(second["cash"], 100.0)
        self.assertEqual(second["positions"], {})
        self.assertEqual(second["closed"], [])
        self.assertEqual(original, frozen)
        self.assertEqual(paper2.baseline_report()["status"], "READY_NOT_RUNNING")

    def test_missing_ledger_fails_closed_instead_of_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                paper2.load_existing(Path(folder) / "missing.json")

    def test_rejects_other_portfolio_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            path.write_text('{"version":1,"portfolio_id":"control","cash":100}')
            with self.assertRaises(ValueError):
                paper2.load_existing(path)

    def test_observe_rejects_control_state(self):
        with self.assertRaises(ValueError):
            paper2.observe(brain.new_state(), [])


if __name__ == "__main__":
    unittest.main()

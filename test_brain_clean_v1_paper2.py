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

    def test_initialize_once_preserves_existing_cash_and_trades(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper2.json"
            first = paper2.initialize_once(path)
            self.assertEqual(first["cash"], 100.0)
            first["cash"] = 83.5
            first["closed"] = [{"key": "example", "pnl_eur": -1.5}]
            import json
            path.write_text(json.dumps(first), encoding="utf-8")
            with self.assertRaises(FileExistsError):
                paper2.initialize_once(path)
            recovered = paper2.load_existing(path)
            self.assertEqual(recovered["cash"], 83.5)
            self.assertEqual(len(recovered["closed"]), 1)

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

    def test_corrupt_restored_cash_or_positions_fails_closed(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper2.json"
            for cash in (float("nan"), -1, "100", True):
                state = paper2.seed()
                state["cash"] = cash
                path.write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaises(ValueError):
                    paper2.load_existing(path)
            state = paper2.seed()
            state["positions"] = []
            path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaises(ValueError):
                paper2.load_existing(path)

    def test_observe_rejects_control_state(self):
        with self.assertRaises(ValueError):
            paper2.observe(brain.new_state(), [])


if __name__ == "__main__":
    unittest.main()

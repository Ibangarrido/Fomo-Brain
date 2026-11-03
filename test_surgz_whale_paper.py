import json
import tempfile
import unittest
from pathlib import Path
import surgz_whale_paper as whale

class WhaleLedgerTests(unittest.TestCase):
    def test_independent_baseline(self):
        state = whale.seed()
        self.assertEqual(state["cash_eur"], 100.0)
        self.assertEqual(state["positions"], {})
        self.assertEqual(state["wallet_attribution"], "UNVERIFIED")
        self.assertIsNone(whale.report(state)["realizable_equity_eur"])

    def test_observations_never_open_positions_or_spend_cash(self):
        state = whale.seed()
        result = whale.observe(state, {"signature": "sig1", "token": "FLOAT"})
        self.assertFalse(result["paper_entry"])
        self.assertEqual(state["cash_eur"], 100)
        self.assertEqual(state["positions"], {})
        self.assertEqual(whale.observe(state, {"signature": "sig1"})["status"], "DUPLICATE")
        self.assertEqual(len(state["observations"]), 1)

    def test_wrong_portfolio_and_missing_state_fail_closed(self):
        with self.assertRaises(ValueError):
            whale.observe({"portfolio_id": "clean-v1"}, {"signature": "x"})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "missing.json"
            with self.assertRaises(FileNotFoundError):
                whale.load_existing(path)
            path.write_text(json.dumps({"portfolio_id": "clean-v1", "mode": "PAPER_ONLY", "version": 1}))
            with self.assertRaises(ValueError):
                whale.load_existing(path)

if __name__ == "__main__":
    unittest.main()

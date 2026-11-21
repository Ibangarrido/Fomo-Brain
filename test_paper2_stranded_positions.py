import unittest
import copy
from paper2_stranded_positions import quarantine_exact_positions

class StrandedPositionsTest(unittest.TestCase):
    def setUp(self):
        self.state = {"portfolio_id":"clean-v1-paper-2","cash":72.28,
            "positions":{"mint:pool":{"key":"mint:pool","cost":10,"units":100}},
            "closed":[{"key":"old","pnl_eur":-2}],"isolated_positions":{}}
        self.proof = {"mint:pool":{"exit_unexecutable":True,"source":"verified-route-evidence"}}

    def test_preserves_cash_closed_cost_and_input(self):
        before = copy.deepcopy(self.state)
        after = quarantine_exact_positions(self.state,["mint:pool"],self.proof)
        self.assertEqual(self.state,before)
        self.assertEqual(after["cash"],before["cash"])
        self.assertEqual(after["closed"],before["closed"])
        self.assertEqual(after["positions"],{})
        self.assertEqual(after["isolated_positions"]["mint:pool"]["cost"],10)
        self.assertIsNone(after["isolated_positions"]["mint:pool"]["realizable_value_eur"])

    def test_rejects_no_evidence(self):
        with self.assertRaises(ValueError):
            quarantine_exact_positions(self.state,["mint:pool"],{})
        self.assertEqual(len(self.state["positions"]),1)

    def test_no_duplicate_quarantine(self):
        after = quarantine_exact_positions(self.state,["mint:pool"],self.proof)
        with self.assertRaises(ValueError):
            quarantine_exact_positions(after,["mint:pool"],self.proof)

    def test_other_portfolio_forbidden(self):
        self.state["portfolio_id"]="control"
        with self.assertRaises(ValueError):
            quarantine_exact_positions(self.state,["mint:pool"],self.proof)

    def test_atomic_on_missing_key(self):
        before = copy.deepcopy(self.state)
        with self.assertRaises(ValueError):
            quarantine_exact_positions(self.state,["mint:pool","unknown"],self.proof)
        self.assertEqual(self.state,before)

if __name__=="__main__":
    unittest.main()

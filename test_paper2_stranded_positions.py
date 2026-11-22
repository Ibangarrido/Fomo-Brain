import unittest
import copy
from paper2_stranded_positions import quarantine_exact_positions, quarantine_persistent_low_liquidity, quarantine_persistent_missing_quotes

class StrandedPositionsTest(unittest.TestCase):
    def setUp(self):
        self.state = {"portfolio_id":"clean-v1-paper-2","cash":72.28,
            "positions":{"mint:pool":{"key":"mint:pool","cost":10,"units":100}},
            "closed":[{"key":"old","pnl_eur":-2}],"isolated_positions":{}}
        self.proof = {"mint:pool":{"exit_unexecutable":True,"source":"verified-route-evidence"}}

    def test_two_runs_required_for_low_liquidity_quarantine(self):
        first = [{"key":"mint:pool","ts":1000,"price":0.01,"liquidity":250}]
        second = [{"key":"mint:pool","ts":5000,"price":0.01,"liquidity":200}]
        self.assertEqual(quarantine_persistent_low_liquidity(self.state,"run-1",first,1000),[])
        self.assertEqual(quarantine_persistent_low_liquidity(self.state,"run-1",second,5000),[])
        self.assertEqual(quarantine_persistent_low_liquidity(self.state,"run-2",second,5000),["mint:pool"])
        self.assertEqual(self.state["cash"],72.28)
        self.assertEqual(len(self.state["closed"]),1)
        self.assertEqual(len(self.state["isolated_positions"]),1)

    def test_recovered_liquidity_resets_counter(self):
        low = [{"key":"mint:pool","ts":1000,"price":0.01,"liquidity":100}]
        recovered = [{"key":"mint:pool","ts":5000,"price":0.01,"liquidity":20000}]
        quarantine_persistent_low_liquidity(self.state,"run-1",low,1000)
        quarantine_persistent_low_liquidity(self.state,"run-2",recovered,5000)
        self.assertEqual(self.state["stranded_observations"],{})
        self.assertIn("mint:pool",self.state["positions"])

    def test_stale_and_missing_liquidity_do_not_quarantine(self):
        low = [{"key":"mint:pool","ts":1000,"price":0.01,"liquidity":100}]
        quarantine_persistent_low_liquidity(self.state,"run-1",low,1000)
        self.assertEqual(quarantine_persistent_low_liquidity(self.state,"run-2",low,50000),[])
        self.assertIn("mint:pool",self.state["positions"])
        self.assertEqual(self.state["stranded_observations"],{})

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


    def test_missing_quotes_two_runs_isolate_without_sale_or_cash_change(self):
        before = copy.deepcopy(self.state)
        self.assertEqual(quarantine_persistent_missing_quotes(self.state, [], "run-1", 1000), [])
        self.assertEqual(quarantine_persistent_missing_quotes(self.state, [], "run-1", 5000), [])
        self.assertEqual(quarantine_persistent_missing_quotes(self.state, [], "run-2", 5000), ["mint:pool"])
        self.assertEqual(self.state["cash"], before["cash"])
        self.assertEqual(self.state["closed"], before["closed"])
        self.assertEqual(self.state["isolated_positions"]["mint:pool"]["cost"], 10)
        self.assertIsNone(self.state["isolated_positions"]["mint:pool"]["realizable_value_eur"])
        self.assertEqual(quarantine_persistent_missing_quotes(self.state, [], "run-3", 9000), [])

    def test_missing_quotes_recovery_resets_observation(self):
        quarantine_persistent_missing_quotes(self.state, [], "run-1", 1000)
        good = [{"key": "mint:pool", "price": 1.0, "liquidity": 20000}]
        self.assertEqual(quarantine_persistent_missing_quotes(self.state, good, "run-2", 5000), [])
        self.assertEqual(self.state["stranded_missing_quote_observations"], {})
        self.assertEqual(quarantine_persistent_missing_quotes(self.state, [], "run-3", 9000), [])
        self.assertIn("mint:pool", self.state["positions"])

    def test_missing_quotes_not_enabled_for_other_portfolios(self):
        self.state["portfolio_id"] = "paper1"
        with self.assertRaises(ValueError):
            quarantine_persistent_missing_quotes(self.state, [], "run-1", 1000)

if __name__=="__main__":
    unittest.main()

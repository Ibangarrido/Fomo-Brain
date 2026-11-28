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
        isolated = self.state["isolated_positions"]["mint:pool"]
        self.assertEqual(isolated["isolation_status"], "ADMINISTRATIVE_NOT_SOLD")
        self.assertFalse(isolated["isolation_evidence"]["exit_unexecutable"])

    def test_zero_liquidity_requires_explicit_evidence(self):
        for t, run in ((1000, "run-1"), (5000, "run-2")):
            q = {"key":"mint:pool","ts":t,"price":0.01,"liquidity":0}
            self.assertEqual(quarantine_persistent_low_liquidity(self.state,run,[q],t),[])
        self.assertIn("mint:pool",self.state["positions"])
        self.assertEqual(self.state["stranded_observations"],{})

    def test_verified_zero_liquidity_two_runs(self):
        q = {"key":"mint:pool","ts":1000,"price":0.01,"liquidity":0,"liquidity_zero_verified":True}
        self.assertEqual(quarantine_persistent_low_liquidity(self.state,"run-1",[q],1000),[])
        self.assertEqual(quarantine_persistent_low_liquidity(self.state,"run-2",[{**q,"ts":5000}],5000),["mint:pool"])
        self.assertEqual(self.state["cash"],72.28)
        self.assertEqual(len(self.state["closed"]),1)
        self.assertEqual(self.state["isolated_positions"]["mint:pool"]["isolation_status"],"ADMINISTRATIVE_NOT_SOLD")

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
        self.assertEqual(after["isolated_positions"]["mint:pool"]["isolation_status"], "UNEXECUTABLE_NOT_SOLD")

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
        def healthy(t):
            return [{"key":"other:pool","ts":t,"price":1.0,"liquidity":20000}]
        self.assertEqual(quarantine_persistent_missing_quotes(self.state, healthy(1000), "run-1", 1000, confirmed_missing_keys=("mint:pool",)), [])
        self.assertEqual(quarantine_persistent_missing_quotes(self.state, healthy(5000), "run-1", 5000, confirmed_missing_keys=("mint:pool",)), [])
        self.assertEqual(quarantine_persistent_missing_quotes(self.state, healthy(5000), "run-2", 5000, confirmed_missing_keys=("mint:pool",)), ["mint:pool"])
        self.assertEqual(self.state["cash"], before["cash"])
        self.assertEqual(self.state["closed"], before["closed"])
        self.assertEqual(self.state["isolated_positions"]["mint:pool"]["cost"], 10)
        self.assertIsNone(self.state["isolated_positions"]["mint:pool"]["realizable_value_eur"])

    def test_unrelated_healthy_quote_is_not_target_evidence(self):
        for t, run in ((1000, "run-1"), (5000, "run-2")):
            samples = [{"key":"other:pool","ts":t,"price":1.0,"liquidity":20000}]
            self.assertEqual(quarantine_persistent_missing_quotes(self.state, samples, run, t), [])
        self.assertIn("mint:pool", self.state["positions"])
        self.assertEqual(self.state["stranded_missing_quote_observations"], {})

    def test_empty_or_stale_feed_never_quarantines(self):
        healthy = [{"key":"other:pool","ts":1000,"price":1.0,"liquidity":20000}]
        quarantine_persistent_missing_quotes(self.state, healthy, "run-1", 1000)
        self.assertEqual(quarantine_persistent_missing_quotes(self.state, [], "run-2", 5000), [])
        self.assertEqual(quarantine_persistent_missing_quotes(self.state, healthy, "run-3", 50000), [])
        self.assertIn("mint:pool", self.state["positions"])
        self.assertEqual(self.state["stranded_missing_quote_observations"], {})

    def test_missing_quotes_recovery_resets_observation(self):
        quarantine_persistent_missing_quotes(self.state, [{"key":"other:pool","ts":1000,"price":1.0,"liquidity":20000}], "run-1", 1000, confirmed_missing_keys=("mint:pool",))
        self.assertIn("mint:pool", self.state["stranded_missing_quote_observations"])
        good = [{"key": "mint:pool", "ts":5000, "price": 1.0, "liquidity": 20000}]
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

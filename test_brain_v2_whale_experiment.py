import unittest
from brain_v2_whale_experiment import compare_fills, watch
class WhaleExperimentTest(unittest.TestCase):
    def test_independent_empty_simulations(self):
        r=compare_fills([],[])
        self.assertEqual(r["baseline"]["cash"],100)
        self.assertEqual(r["whale"]["cash"],100)
        self.assertEqual(r["orders"],[])
    def test_no_evidence_holds(self):
        r=watch(wallets=[],events=[],mint="test",now=10000,radar_inputs=dict(volume_5m=600,previous_volume_5m=200,buyers_5m=15,previous_buyers_5m=8,liquidity=10000,change_5m_pct=10,change_1h_pct=50,quote_age_seconds=1),risk_inputs={})
        self.assertEqual(r["decision"],"HOLD")
        self.assertEqual(r["orders"],[])

import unittest
from brain_v2_profit_experiment import anti_staircase, profit_lock, experiment
class ProfitExperimentTest(unittest.TestCase):
    def test_repeat_crash(self):
        self.assertEqual(anti_staircase([1,2,3,1,2,0.1]),"BLOCK")
    def test_missing_history(self):
        self.assertEqual(anti_staircase([1,2]),"UNKNOWN")
    def test_lock(self):
        self.assertEqual(profit_lock(10,13,15,1,10000,True),"PAPER_EXIT_CANDIDATE")
    def test_no_route(self):
        self.assertEqual(profit_lock(10,13,15,1,10000,False),"QUARANTINE_UNVERIFIED_EXIT")
    def test_no_automatic_promotion(self):
        r=experiment(prices=[1,1.1,1.2,1.3,1.4,1.5],radar_inputs=dict(volume_5m=600,previous_volume_5m=200,buyers_5m=15,previous_buyers_5m=8,liquidity=10000,change_5m_pct=10,change_1h_pct=50,quote_age_seconds=1),records=[],baseline=[],challenger=[],as_of=10000,selection_cutoff=0)
        self.assertEqual(r["sniper"],"WATCH_ONLY")
        self.assertEqual(r["autotest"]["decision"],"INSUFFICIENT_EVIDENCE")
        self.assertEqual(r["orders"],[])
        self.assertEqual(len(r["shadow"]),4)

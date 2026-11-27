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


class StaircaseWatchTests(unittest.TestCase):
    def case(self, prices, wrong_pool=False, future=False):
        from brain_v2_profit_experiment import staircase_watch
        rows=[dict(mint="m",pair="p",source="dexscreener",received_at=100+i*30,price_usd=p) for i,p in enumerate(prices)]
        if wrong_pool: rows[-1]["pair"]="other"
        return staircase_watch(rows,as_of=rows[-1]["received_at"]-(1 if future else 0))
    def test_repeated_crash(self):
        r=self.case([1,2,.2,.4,.8,.1])
        self.assertEqual(r["status"],"REPEAT_CRASH_ALERT")
        self.assertEqual(r["orders"],[])
    def test_healthy(self):
        self.assertEqual(self.case([1,1.2,1.1,1.4,1.3,1.6])["status"],"NO_REPEAT_FLAG")
    def test_single_crash(self):
        self.assertEqual(self.case([1,2,.2,.19,.18,.17])["status"],"WATCH")
    def test_wrong_pool(self):
        self.assertEqual(self.case([1,2,.2,.4,.8,.1],wrong_pool=True)["status"],"UNKNOWN")
    def test_future(self):
        self.assertEqual(self.case([1,2,.2,.4,.8,.1],future=True)["status"],"UNKNOWN")


class PartialProfitTests(unittest.TestCase):
    def plan(self, price, peak, completed=(), route=True):
        from brain_v2_profit_experiment import partial_profit_plan
        return partial_profit_plan(10,price,peak,1,10000,route,completed)
    def test_thresholds(self):
        self.assertEqual([x["level_pct"] for x in self.plan(30,30)["candidates"]],[50,100,200])
    def test_no_duplicate_completed(self):
        r=self.plan(30,30,(50,100))
        self.assertEqual([x["level_pct"] for x in r["candidates"]],[200])
        self.assertEqual(r["remaining_fraction"],.5)
        self.assertEqual(r["orders"],[])
    def test_invalid_history(self):
        self.assertEqual(self.plan(30,30,(100,))["status"],"UNKNOWN_HISTORY")
    def test_unverified_route(self):
        self.assertEqual(self.plan(30,30,route=False)["candidates"],[])
    def test_retracement(self):
        self.assertEqual(self.plan(13,15)["status"],"PAPER_EXIT_CANDIDATE")

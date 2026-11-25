import unittest
from brain_v2_whale import classify

class WhaleTests(unittest.TestCase):
    def event(self,i,**kw):
        return dict(dict(wallet="w",mint="m",timestamp=100+i,usd=40,signature=str(i),instruction_index=0,side="buy",verified=True),**kw)
    def run_events(self,events):
        return classify(events,wallet="w",mint="m",now=200)
    def test_accumulation(self):
        self.assertEqual(self.run_events([self.event(i) for i in range(3)])["label"],"ACCUMULATION_WATCH")
    def test_duplicate(self):
        self.assertEqual(self.run_events([self.event(1)]*3)["buy_count"],1)
    def test_unverified(self):
        self.assertEqual(self.run_events([self.event(1,verified=False)])["buy_count"],0)
    def test_future(self):
        self.assertEqual(self.run_events([self.event(1,timestamp=201)])["buy_count"],0)
    def test_wrong_wallet(self):
        self.assertEqual(self.run_events([self.event(1,wallet="other")])["buy_count"],0)
    def test_distribution(self):
        self.assertEqual(self.run_events([self.event(i,side="sell",usd=60) for i in range(2)])["label"],"DISTRIBUTION_WATCH")
    def test_conflict(self):
        with self.assertRaises(ValueError):
            self.run_events([self.event(1),self.event(1,usd=90)])
    def test_isolated(self):
        self.assertEqual(self.run_events([self.event(1,usd=1000)])["label"],"MIXED_OR_ISOLATED")

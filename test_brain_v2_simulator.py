import unittest
from brain_v2_simulator import replay

class SimulatorTests(unittest.TestCase):
    def event(self,i,side="buy",**kw):
        return dict(dict(id=str(i),mint="m",timestamp=i+1,signal_at=i,price=1,eur=10,side=side,executable=True),**kw)
    def test_costs(self):
        r=replay([self.event(1),self.event(2,"sell")])
        self.assertAlmostEqual(r["cash"],90+10*.996**2)
    def test_gain(self):
        self.assertGreater(replay([self.event(1),self.event(2,"sell",price=2)])["realized_pnl"],0)
    def test_open_unknown(self):
        self.assertIsNone(replay([self.event(1)])["net_return_pct"])
    def test_duplicate(self):
        with self.assertRaises(ValueError): replay([self.event(1)]*2)
    def test_future(self):
        with self.assertRaises(ValueError): replay([self.event(1,signal_at=3)])
    def test_unverified(self):
        with self.assertRaises(ValueError): replay([self.event(1,executable=False)])
    def test_limit(self):
        with self.assertRaises(ValueError): replay([self.event(1,eur=11)])
    def test_slots(self):
        with self.assertRaises(ValueError): replay([self.event(i,mint=str(i)) for i in range(4)])
    def test_no_position(self):
        with self.assertRaises(ValueError): replay([self.event(1,"sell")])
    def test_loss(self):
        r=replay([self.event(1),self.event(2,"sell",price=.01)])
        self.assertEqual(r["losses"],1)
        self.assertGreater(r["flat_checkpoint_drawdown_pct"],9)

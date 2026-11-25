import unittest
from brain_v2_memory import record, observe

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.j = {}
        self.args = dict(mint="example",chain="solana",timestamp=1000,price=1,
                         decision="discard",reason="liquidity",features={"volume":500},strategy="radar-v1")
        self.key = record(self.j, **self.args)
    def test_duplicate(self):
        self.assertEqual(record(self.j, **self.args), self.key)
        self.assertEqual(len(self.j),1)
    def test_conflict(self):
        with self.assertRaises(ValueError):
            record(self.j, **dict(self.args,reason="other"))
    def test_future(self):
        with self.assertRaises(ValueError):
            observe(self.j,self.key,timestamp=1300,price=2,observed_at=1299)
    def test_early(self):
        self.assertIsNone(observe(self.j,self.key,timestamp=1299,price=2,observed_at=1300))
    def test_mature(self):
        self.assertEqual(observe(self.j,self.key,timestamp=1300,price=1.5,observed_at=1300),"300")
        self.assertEqual(self.j[self.key]["outcomes"]["300"]["gross_return_pct"],50)
    def test_late(self):
        self.assertIsNone(observe(self.j,self.key,timestamp=1361,price=2,observed_at=1361))
    def test_missing_price(self):
        with self.assertRaises(ValueError):
            observe(self.j,self.key,timestamp=1300,price=None,observed_at=1300)
    def test_snapshot(self):
        self.args["features"]["volume"]=0
        self.assertEqual(self.j[self.key]["decision"]["features"]["volume"],500)

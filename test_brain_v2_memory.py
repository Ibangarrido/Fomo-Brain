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

    def test_discard_review_cutoff(self):
        from brain_v2_memory import discard_review
        observe(self.j,self.key,timestamp=2800,price=5,observed_at=2900)
        self.assertEqual(discard_review(self.j,as_of=2850)["counts"]["pending"],1)
        r=discard_review(self.j,as_of=2900)
        self.assertEqual(r["counts"]["matured"],1)
        self.assertEqual(r["counts"]["rally_5x"],1)
        self.assertEqual(r["orders"],[])
    def test_legacy_replay_does_not_invent_receipt(self):
        from brain_v2_memory import discard_review
        observe(self.j,self.key,timestamp=2800,price=2,observed_at=2900)
        del self.j[self.key]["outcome_received_at"]
        observe(self.j,self.key,timestamp=2800,price=2,observed_at=3000)
        self.assertEqual(discard_review(self.j,as_of=3100)["counts"]["pending"],1)
    def test_receipt_immutable(self):
        observe(self.j,self.key,timestamp=2800,price=2,observed_at=2900)
        observe(self.j,self.key,timestamp=2800,price=2,observed_at=3000)
        self.assertEqual(self.j[self.key]["outcome_received_at"]["1800"],2900)

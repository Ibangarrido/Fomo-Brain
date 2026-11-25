import unittest
from brain_v2_replay import review

class ReplayTests(unittest.TestCase):
    def row(self,price=1.5,**kw):
        return dict(dict(id="a",timestamp=100,price=1,decision="HOLD",reason="FILTER",observations=[dict(timestamp=3700,observed_at=3701,price=price,verified=True)]),**kw)
    def test_rally(self):
        self.assertEqual(review([self.row()],as_of=4000)["counts"],{"RALLY_AFTER_DISCARD":1})
    def test_drop(self):
        self.assertEqual(review([self.row(.01)],as_of=4000)["counts"],{"DROP_AFTER_DISCARD":1})
    def test_neutral(self):
        self.assertEqual(review([self.row(1)],as_of=4000)["counts"],{"NEUTRAL":1})
    def test_future(self):
        self.assertEqual(review([self.row()],as_of=3700)["counts"],{"PENDING":1})
    def test_missing(self):
        self.assertEqual(review([self.row(observations=[])],as_of=4000)["counts"],{"MISSING_OUTCOME":1})
    def test_duplicate(self):
        self.assertEqual(len(review([self.row()]*2,as_of=4000)["rows"]),1)
    def test_conflict(self):
        with self.assertRaises(ValueError): review([self.row(),self.row(.5)],as_of=4000)
    def test_unverified(self):
        self.assertEqual(review([self.row(observations=[dict(timestamp=3700,observed_at=3701,price=2,verified=False)])],as_of=4000)["counts"],{"MISSING_OUTCOME":1})
    def test_no_orders(self):
        self.assertEqual(review([self.row()],as_of=4000)["orders"],[])

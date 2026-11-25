import unittest
from brain_v2_predictor import describe

class PredictorTests(unittest.TestCase):
    def case(self,i,**kw):
        t=100000+i*86400
        return dict(dict(id=str(i),timestamp=t,outcome_at=t+3600,return_pct=30 if i%2 else -30,features=[i/100],verified=True),**kw)
    def run_cases(self,cases):
        return describe([0],cases,as_of=2000000)
    def test_maximum(self):
        self.assertEqual(self.run_cases([self.case(i) for i in range(12)])["count"],10)
    def test_minimum(self):
        self.assertIsNone(self.run_cases([self.case(i) for i in range(7)])["fractions"])
    def test_fractions(self):
        r=self.run_cases([self.case(i) for i in range(8)])
        self.assertEqual(r["fractions"],dict(rally=.5,drop=.5,neutral=0))
        self.assertFalse(r["entry_filter"])
    def test_future(self):
        self.assertEqual(self.run_cases([self.case(1,timestamp=2000000,outcome_at=2003600)])["count"],0)
    def test_duplicate(self):
        self.assertEqual(self.run_cases([self.case(1)]*3)["count"],1)
    def test_separation(self):
        self.assertEqual(self.run_cases([self.case(0),self.case(1,timestamp=100001,outcome_at=103601)])["count"],1)
    def test_unverified(self):
        self.assertEqual(self.run_cases([self.case(1,verified=False)])["count"],0)
    def test_wrong_horizon(self):
        self.assertEqual(self.run_cases([self.case(0,outcome_at=100001)])["count"],0)
    def test_conflict(self):
        with self.assertRaises(ValueError):
            self.run_cases([self.case(1),self.case(1,return_pct=99)])

import unittest
from brain_v2_adaptive import evaluate

class AdaptiveTests(unittest.TestCase):
    def rows(self,n=20,net=1,dd=2):
        return [dict(start=100+i*10,end=110+i*10,net_pct=net,drawdown_pct=dd,verified=True,costs_included=True) for i in range(n)]
    def run_case(self,a,b):
        return evaluate(a,b,as_of=400,selection_cutoff=100)
    def test_candidate(self):
        self.assertEqual(self.run_case(self.rows(),self.rows(net=2))["decision"],"REVIEW_CANDIDATE")
    def test_insufficient(self):
        self.assertEqual(self.run_case(self.rows(5),self.rows(5))["decision"],"INSUFFICIENT_EVIDENCE")
    def test_risk(self):
        self.assertEqual(self.run_case(self.rows(),self.rows(net=2,dd=3))["decision"],"KEEP_BASELINE")
    def test_loss(self):
        self.assertEqual(self.run_case(self.rows(net=-3),self.rows(net=-1))["decision"],"KEEP_BASELINE")
    def test_unmatched(self):
        self.assertEqual(self.run_case(self.rows(),self.rows(19))["decision"],"UNMATCHED_WINDOWS")
    def test_future(self):
        a=self.rows();a[-1]["end"]=401
        with self.assertRaises(ValueError): self.run_case(a,a)
    def test_overlap(self):
        a=self.rows();a[0]["end"]=115
        with self.assertRaises(ValueError): self.run_case(a,a)
    def test_duplicate(self):
        a=self.rows();a.append(a[0])
        with self.assertRaises(ValueError): self.run_case(a,a)
    def test_costs(self):
        a=self.rows();a[0]["costs_included"]=False
        with self.assertRaises(ValueError): self.run_case(a,a)
    def test_no_mutation(self):
        r=self.run_case(self.rows(),self.rows(net=2))
        self.assertEqual(r["changes"],[])
        self.assertEqual(r["orders"],[])

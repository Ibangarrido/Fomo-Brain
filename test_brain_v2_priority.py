import unittest
from brain_v2_priority import plan,estimated_cost
class PriorityTest(unittest.TestCase):
    def test_exit_first(self):
        r=plan([dict(id="a",kind="WHALE",route_verified=True,fresh_quote=True),dict(id="b",kind="STOP",route_verified=True,fresh_quote=True)])
        self.assertEqual([x["status"] for x in r["queue"]],["PAPER_EXIT_CANDIDATE","DEFERRED_EXIT_PENDING"])
        self.assertEqual(r["orders"],[])
    def test_unverified_exit(self):
        self.assertEqual(plan([dict(id="a",kind="EMERGENCY")])["queue"][0]["status"],"EXIT_UNVERIFIED")
    def test_duplicate(self):
        with self.assertRaises(ValueError): plan([dict(id="a",kind="STOP")]*2)
    def test_cost(self):
        self.assertAlmostEqual(estimated_cost(10,20,20,.01),.05)
    def test_unknown_cost(self):
        with self.assertRaises(ValueError): estimated_cost(10,20,20,None)

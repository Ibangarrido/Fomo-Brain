import unittest
from brain_v2_guardian import assess

class GuardianTests(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(assess(1,None,1,9000,True),"QUARANTINE_MISSING_QUOTE")
    def test_stale(self):
        self.assertEqual(assess(1,.01,97*60,9000,True),"QUARANTINE_STALE_QUOTE")
    def test_zero(self):
        self.assertEqual(assess(1,0,1,9000,True),"QUARANTINE_ZERO_QUOTE")
    def test_no_route(self):
        self.assertEqual(assess(1,.01,1,9000,False),"QUARANTINE_UNVERIFIED_EXIT")
    def test_low_liquidity(self):
        self.assertEqual(assess(1,.01,1,10,True),"QUARANTINE_UNVERIFIED_EXIT")
    def test_drop(self):
        self.assertEqual(assess(1,.01,1,9000,True),"PAPER_EXIT_CANDIDATE")
    def test_healthy(self):
        self.assertEqual(assess(1,1.1,1,9000,True),"MONITOR")
    def test_invalid(self):
        self.assertEqual(assess(0,1,1,9000,True),"INVALID_ENTRY")

import unittest
from brain_v2_market import observe
class MarketTests(unittest.TestCase):
    def test_observed_not_executable(self):
        r=observe(["A"*32],fetcher=lambda m:[{"price_usd":1}])[0]
        self.assertEqual(r["decision"],"HOLD")
        self.assertEqual(r["risk"]["status"],"UNKNOWN_BLOCK")
        self.assertEqual(r["orders"],[])
    def test_empty(self):
        self.assertEqual(observe(["A"*32],fetcher=lambda m:[])[0]["source_status"],"NO_DATA")
    def test_error(self):
        def fail(m): raise TimeoutError()
        self.assertEqual(observe(["A"*32],fetcher=fail)[0]["source_status"],"SOURCE_ERROR")

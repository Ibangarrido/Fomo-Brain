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
        row=observe(["A"*32],fetcher=fail)[0]
        self.assertEqual(row["source_status"],"SOURCE_ERROR")
        self.assertEqual(row["source_error"],"TimeoutError")
        self.assertEqual(row["decision"],"HOLD")
        self.assertEqual(row["observations"],[])
        self.assertEqual(row["orders"],[])
        self.assertEqual(row["risk"]["status"],"UNKNOWN_BLOCK")

    def test_fallback_observation_only(self):
        def fail(m): raise TimeoutError()
        def fallback(m):
            return {"mint":m,"sources":{"geckoterminal":{"status":"OK","data":{"price_usd":1}}}}
        row=observe(["A"*32],fetcher=fail,fallback=fallback)[0]
        self.assertEqual(row["source_status"],"SOURCE_ERROR")
        self.assertEqual(row["fallback_sources"]["geckoterminal"]["status"],"OK")
        self.assertEqual(row["decision"],"HOLD")
        self.assertEqual(row["orders"],[])
    def test_fallback_wrong_mint(self):
        row=observe(["A"*32],fetcher=lambda m:[],fallback=lambda m:{"mint":"wrong","sources":{}})[0]
        self.assertEqual(row["fallback_error"],"ValueError")
        self.assertNotIn("fallback_sources",row)
    def test_primary_success_skips_fallback(self):
        def fallback(m): self.fail("unexpected fallback")
        row=observe(["A"*32],fetcher=lambda m:[{"price_usd":1}],fallback=fallback)[0]
        self.assertEqual(row["source_status"],"OK")
        self.assertNotIn("fallback_error",row)

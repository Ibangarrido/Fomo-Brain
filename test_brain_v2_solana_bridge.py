import unittest
from urllib.error import HTTPError
from brain_v2_solana_bridge import bridge
M="So11111111111111111111111111111111111111112"
class BridgeTests(unittest.TestCase):
    def transport(self,url,payload=None):
        if payload: return {"id":1,"result":{"context":{"slot":123},"value":{"owner":"token","data":{"parsed":{"type":"mint","info":{"mintAuthority":None,"freezeAuthority":"a","supply":"1000","decimals":9}}}}}}
        if "dexscreener" in url: return [{"chainId":"solana","baseToken":{"address":M},"pairAddress":"pool","priceUsd":"1","liquidity":{"usd":10000}}]
        return {"data":{"attributes":{"address":M,"price_usd":"1.01"}}}
    def test_sources(self):
        r=bridge(M,transport=self.transport)
        self.assertTrue(all(s["status"]=="OK" for s in r["sources"].values()))
    def test_authority(self):
        self.assertTrue(bridge(M,transport=self.transport)["sources"]["solana_rpc"]["data"]["freeze_authority_active"])
    def test_no_execution(self):
        r=bridge(M,transport=self.transport)
        self.assertEqual(r["orders"],[])
        self.assertIsNone(r["quote_timestamp"])
        self.assertFalse(r["route_verified"])
    def test_fallback(self):
        def f(url,payload=None):
            if "dexscreener" in url: raise HTTPError(url,429,"rate",{},None)
            return self.transport(url,payload)
        r=bridge(M,transport=f)["sources"]
        self.assertEqual(r["dexscreener"]["http_status"],429)
        self.assertEqual(r["geckoterminal"]["status"],"OK")
    def test_empty(self):
        def f(url,payload=None): return [] if "dexscreener" in url else self.transport(url,payload)
        self.assertEqual(bridge(M,transport=f)["sources"]["dexscreener"]["status"],"NO_DATA")
    def test_wrong_token(self):
        def f(url,payload=None): return {"data":{"attributes":{"address":"wrong","price_usd":"1"}}} if "gecko" in url else self.transport(url,payload)
        self.assertEqual(bridge(M,transport=f)["sources"]["geckoterminal"]["status"],"SOURCE_ERROR")
    def test_invalid(self):
        with self.assertRaises(ValueError): bridge("../bad",transport=self.transport)

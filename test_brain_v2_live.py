import io
import json
import unittest
from brain_v2_live import fetch,poll

M="A"*32
class LiveTests(unittest.TestCase):
    def row(self,**kw):
        return dict(dict(chainId="solana",baseToken={"address":M},priceUsd="1",liquidity={"usd":6000},pairAddress="p"),**kw)
    def get(self,rows):
        return fetch(M,opener=lambda *a,**k:io.BytesIO(json.dumps(rows).encode()),clock=lambda:123)
    def test_provenance(self):
        r=self.get([self.row()])[0]
        self.assertIsNone(r["quote_timestamp"])
        self.assertFalse(r["route_verified"])
        self.assertEqual(r["received_at"],123)
    def test_wrong_chain(self):
        self.assertEqual(self.get([self.row(chainId="ethereum")]),[])
    def test_wrong_mint(self):
        self.assertEqual(self.get([self.row(baseToken={"address":"other"})]),[])
    def test_invalid_price(self):
        self.assertEqual(self.get([self.row(priceUsd="nan")]),[])
    def test_bad_mint(self):
        with self.assertRaises(ValueError): fetch("../")
    def test_recovery(self):
        calls=[]
        def f(m):
            calls.append(m)
            if len(calls)==1: raise TimeoutError()
            return [{}]
        delays=[]
        r=list(poll([M],fetcher=f,rounds=2,sleep=delays.append))
        self.assertEqual([x[0]["status"] for x in r],["SOURCE_ERROR","OK"])
        self.assertEqual(delays,[60])
    def test_dedup(self):
        self.assertEqual(len(next(poll([M,M],fetcher=lambda m:[]))),1)
    def test_budget(self):
        with self.assertRaises(ValueError): list(poll([M],interval=1))

    def test_fetch_retry_recovers(self):
        calls, delays = [], []
        def opener(*args, **kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise TimeoutError()
            return io.BytesIO(json.dumps([self.row()]).encode())
        rows = fetch(M, opener=opener, sleep=delays.append)
        self.assertEqual(len(rows), 1)
        self.assertEqual(delays, [1, 2])
        self.assertFalse(rows[0]["route_verified"])
    def test_fetch_retry_exhausted(self):
        calls, delays = [], []
        def opener(*args, **kwargs):
            calls.append(1)
            raise TimeoutError()
        with self.assertRaises(TimeoutError):
            fetch(M, opener=opener, sleep=delays.append)
        self.assertEqual(len(calls), 3)
        self.assertEqual(delays, [1, 2])
    def test_fetch_no_retry_forbidden(self):
        from urllib.error import HTTPError
        delays = []
        def opener(*args, **kwargs):
            raise HTTPError("https://example.invalid", 403, "Forbidden", None, None)
        with self.assertRaises(HTTPError):
            fetch(M, opener=opener, sleep=delays.append)
        self.assertEqual(delays, [])


class TurboTests(unittest.TestCase):
    def plan(self, targets, **kwargs):
        from brain_v2_live import turbo_plan
        return turbo_plan(targets, **dict(dict(now=100,last_attempt={}),**kwargs))
    def test_priority_budget_dedup(self):
        targets=[dict(kind=k,key="a") for k in ("market","whale","candidate","position","position")]
        r=self.plan(targets,budget=3)
        self.assertEqual([x["kind"] for x in r["due"]],["position","candidate","whale"])
        self.assertEqual(r["orders"],[])
    def test_cadence(self):
        targets=[dict(kind=k,key="a") for k in ("position","candidate","whale","market")]
        r=self.plan(targets,last_attempt={(k,"a"):85 for k in ("position","candidate","whale","market")})
        self.assertEqual([x["kind"] for x in r["due"]],["position","candidate"])
    def test_backoff(self):
        self.assertEqual(self.plan([dict(kind="position",key="a")],blocked_until=101)["due"],[])
    def test_future_attempt(self):
        with self.assertRaises(ValueError):
            self.plan([dict(kind="position",key="a")],last_attempt={("position","a"):101})

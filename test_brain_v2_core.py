import unittest
from datetime import datetime, timezone
from copy import deepcopy
from brain_v2_core import cycle

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,25,tzinfo=timezone.utc)
        self.state=dict(portfolio_id="clean-v1-paper-2",cash=100,closed=[],positions={},last_run=dict(completed_at=self.now.isoformat()))
        self.c=dict(mint="m",chain="solana",wallet="w",features=[0],
            risk=dict(entry=1,price=1,quote_age=1,liquidity=6000,route_verified=True),
            radar=dict(volume_5m=600,previous_volume_5m=200,buyers_5m=15,previous_buyers_5m=5,liquidity=6000,change_5m_pct=10,change_1h_pct=20,quote_age_seconds=1))
    def run_cycle(self,candidates=None,journal=None):
        return cycle(state=self.state,previous=None,now=self.now,candidates=[self.c] if candidates is None else candidates,journal={} if journal is None else journal)
    def test_watch(self):
        r=self.run_cycle()
        self.assertEqual(r["decisions"][0]["decision"],"WATCH_ONLY")
        self.assertEqual(r["orders"],[])
        self.assertEqual(len(r["journal"]),1)
        self.assertEqual(r["errors"],[])
    def test_health_block(self):
        self.state["cash"]=-1
        self.assertEqual(self.run_cycle()["decisions"][0]["decision"],"HOLD")
    def test_risk_block(self):
        self.c["risk"]["route_verified"]=False
        self.assertEqual(self.run_cycle()["decisions"][0]["decision"],"HOLD")
    def test_isolation(self):
        r=self.run_cycle([{},self.c])
        self.assertEqual([x["decision"] for x in r["decisions"]],["HOLD","WATCH_ONLY"])
    def test_read_only(self):
        before=deepcopy(self.state)
        j={}
        self.run_cycle(journal=j)
        self.assertEqual(self.state,before)
        self.assertEqual(j,{})
    def test_repeat(self):
        r=self.run_cycle()
        self.assertEqual(len(self.run_cycle(journal=r["journal"])["journal"]),1)
    def test_simulator(self):
        self.assertEqual(self.run_cycle()["simulation"]["cash"],100)

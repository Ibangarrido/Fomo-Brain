import unittest
from datetime import datetime, timezone
from brain_v2_core import cycle

class ScenarioTests(unittest.TestCase):
    def test_market_replay(self):
        now=datetime(2026,11,25,tzinfo=timezone.utc)
        state=dict(portfolio_id="clean-v1-paper-2",cash=100,closed=[],positions={},last_run=dict(completed_at=now.isoformat()))
        def candidate(mint,price,route=True):
            return dict(mint=mint,chain="solana",wallet="w",features=[0],
                risk=dict(entry=1,price=price,quote_age=1,liquidity=6000,route_verified=route),
                radar=dict(volume_5m=600,previous_volume_5m=200,buyers_5m=15,previous_buyers_5m=5,liquidity=6000,change_5m_pct=10,change_1h_pct=20,quote_age_seconds=1))
        def fill(i,mint,side,price):
            return dict(id=str(i),mint=mint,side=side,price=price,eur=10,timestamp=i+1,signal_at=i,executable=True)
        r=cycle(state=state,previous=None,now=now,candidates=[candidate("rise",1),candidate("crash",.01),candidate("missing",None),candidate("no-route",1,False)],journal={},fills=[fill(1,"rise","buy",1),fill(2,"rise","sell",1.5),fill(3,"crash","buy",1),fill(4,"crash","sell",.01)])
        self.assertEqual([x["decision"] for x in r["decisions"]],["WATCH_ONLY","HOLD","HOLD","HOLD"])
        self.assertEqual(r["orders"],[])
        self.assertEqual(state["cash"],100)
        self.assertAlmostEqual(r["simulation"]["cash"],80+15.1*.996**2)
        self.assertEqual(r["simulation"]["closed_count"],2)
        print("SYNTHETIC_SCENARIO",r["simulation"],r["decisions"])

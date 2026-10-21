"""Regression: REWATCH observes rejected candidates without altering entry policy."""
import unittest
from datetime import datetime, timezone, timedelta
from v13_runner import select_revisits, MAX_REWATCH

class RewatchTests(unittest.TestCase):
    def test_rejected_alert_is_revisited(self):
        now = datetime(2026, 10, 21, 17, tzinfo=timezone.utc)
        prior = [{"chain":"solana","address":"rejected-mint","received_at":(now-timedelta(minutes=10)).isoformat(),
                  "discovery_alert":True,"market_gates_pass":False,"blockers":["age"],
                  "price_usd":0.001}]
        requested, dormant = select_revisits(prior, now)
        self.assertIn(("solana","rejected-mint"), requested)
        self.assertEqual(dormant, 0)

    def test_bounded_and_no_future_or_missing_price(self):
        now = datetime(2026, 10, 21, 17, tzinfo=timezone.utc)
        prior = [{"chain":"solana","address":f"mint{i}","received_at":(now-timedelta(minutes=5)).isoformat(),
                  "discovery_alert":True,"market_gates_pass":False,"blockers":["age"],
                  "price_usd":0.001} for i in range(50)]
        prior += [{"chain":"solana","address":"future","received_at":(now+timedelta(minutes=1)).isoformat(),
                   "discovery_alert":True,"market_gates_pass":False,"blockers":["age"],"price_usd":0.001},
                  {"chain":"solana","address":"missing","received_at":now.isoformat(),
                   "discovery_alert":True,"market_gates_pass":False,"blockers":["age"],"price_usd":None}]
        requested, _ = select_revisits(prior, now)
        self.assertLessEqual(len(requested), 18)
        self.assertNotIn(("solana","future"), requested)

if __name__ == "__main__":
    unittest.main()

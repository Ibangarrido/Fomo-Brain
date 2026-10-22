"""Regression: REWATCH observes rejected candidates without altering entry policy."""
import unittest
from datetime import datetime, timezone, timedelta
from v13_runner import select_revisits, MAX_REWATCH

class RewatchTests(unittest.TestCase):
    def test_rejected_alert_is_revisited(self):
        now = datetime(2026, 10, 21, 17, tzinfo=timezone.utc)
        prior = [{"chain":"solana","address":"rejected-mint","received_at":(now-timedelta(minutes=10)).isoformat(),
                  "discovery_alert":False,"market_gates_pass":False,"blockers":["age"],
                  "price_usd":0.001}]
        requested, dormant = select_revisits(prior, now)
        self.assertIn(("solana","rejected-mint"), requested)
        self.assertEqual(dormant, 0)

    def test_bounded_and_no_future_or_missing_price(self):
        now = datetime(2026, 10, 21, 17, tzinfo=timezone.utc)
        prior = [{"chain":"solana","address":f"mint{i:03}",
                  "received_at":(now-timedelta(minutes=5)).isoformat(),
                  "discovery_alert":False,"market_gates_pass":False,
                  "blockers":["age"],"price_usd":0.001} for i in range(50)]
        prior += [{"chain":"solana","address":"future",
                   "received_at":(now+timedelta(minutes=1)).isoformat(),
                   "discovery_alert":False,"market_gates_pass":False,
                   "blockers":["age"],"price_usd":0.001},
                  {"chain":"solana","address":"missing","received_at":now.isoformat(),
                   "discovery_alert":False,"market_gates_pass":False,
                   "blockers":["age"],"price_usd":None}]
        requested, _ = select_revisits(prior, now)
        self.assertEqual(len(requested), MAX_REWATCH)
        self.assertNotIn(("solana","future"), requested)
        self.assertNotIn(("solana","missing"), requested)

    def test_rotation_changes_selected_contracts(self):
        now = datetime(2026, 10, 21, 17, tzinfo=timezone.utc)
        prior = [{"chain":"solana","address":f"mint{i:03}",
                  "received_at":(now-timedelta(minutes=1)).isoformat(),
                  "discovery_alert":False,"market_gates_pass":False,
                  "blockers":["age"],"price_usd":0.001} for i in range(40)]
        first, _ = select_revisits(prior, now)
        second, _ = select_revisits(prior, now+timedelta(minutes=20))
        self.assertEqual(len(first), MAX_REWATCH)
        self.assertEqual(len(second), MAX_REWATCH)
        self.assertNotEqual(first, second)

    def test_existing_alerts_are_not_double_counted(self):
        now = datetime(2026, 10, 21, 17, tzinfo=timezone.utc)
        prior = [{"chain":"solana","address":"alert","received_at":now.isoformat(),
                  "discovery_alert":True,"market_gates_pass":False,
                  "blockers":["age"],"price_usd":0.001}]
        requested, _ = select_revisits(prior, now)
        self.assertEqual(requested, (("solana","alert"),))

if __name__ == "__main__":
    unittest.main()

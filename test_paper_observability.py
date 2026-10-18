import unittest
from datetime import datetime, timedelta, timezone
from paper_observability import observe_rejection, net_paper_exit


class PaperObservabilityTests(unittest.TestCase):
    def test_forward_returns_and_missing(self):
        t = datetime(2026, 10, 18, tzinfo=timezone.utc)
        observations = [{"timestamp": t + timedelta(minutes=6), "price": 110},
                        {"timestamp": t + timedelta(minutes=16), "price": 90}]
        r = observe_rejection("mint1", t, 100, observations)
        self.assertEqual(r["forward_returns_pct"]["5"], 10)
        self.assertEqual(r["forward_returns_pct"]["15"], -10)
        self.assertIsNone(r["forward_returns_pct"]["30"])

    def test_bad_quotes_never_create_profit(self):
        self.assertIsNone(net_paper_exit(1, 10, None)["net_pnl"])
        self.assertEqual(net_paper_exit(1, 10, 12, 0.5, 0.5, 0.25)["net_pnl"], 0.75)

    def test_reject_naive_datetime(self):
        with self.assertRaises(ValueError):
            observe_rejection("mint1", datetime(2026, 1, 1), 100, [])


if __name__ == "__main__":
    unittest.main()

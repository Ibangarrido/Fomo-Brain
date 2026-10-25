import unittest
from datetime import datetime, timedelta, timezone
from recovery_watch import evaluate_recovery


class RecoveryWatchTests(unittest.TestCase):
    def snapshots(self, prices, ratios=None):
        start = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)
        return [
            {"timestamp": (start + timedelta(minutes=i)).isoformat(),
             "price": price, "liquidity_usd": 20000,
             "buy_ratio": ratios[i] if ratios else .70,
             "volume_5m": 100 + i * 10}
            for i, price in enumerate(prices)
        ]

    def test_recovery_after_pullback(self):
        data = self.snapshots([100, 110, 95, 96, 99])
        result = evaluate_recovery(data, data[0]["timestamp"])
        self.assertEqual(result["status"], "PAPER_SIGNAL")

    def test_no_signal_without_pullback(self):
        data = self.snapshots([100, 102, 104, 106])
        self.assertEqual(evaluate_recovery(data, data[0]["timestamp"])["status"], "WATCH")

    def test_low_buy_ratio_blocks(self):
        data = self.snapshots([100, 110, 95, 96, 99], [.4] * 5)
        self.assertEqual(evaluate_recovery(data, data[0]["timestamp"])["status"], "WATCH")

    def test_missing_data_does_not_trigger(self):
        self.assertEqual(evaluate_recovery([], "2026-10-25T10:00:00Z")["status"], "NO_DATA")


if __name__ == "__main__":
    unittest.main()

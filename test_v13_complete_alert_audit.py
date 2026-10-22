"""Regression: V13 retains every alert while dashboard preview stays capped."""
import unittest
from v13_runner import ranked_discovery_alerts


class CompleteAlertAuditTests(unittest.TestCase):
    def test_over_thirty_alerts_preserved_and_ranked(self):
        rows = [
            {"discovery_alert": True, "market_gates_pass": i == 34,
             "trades_5m": i, "address": f"token-{i}"}
            for i in range(35)
        ]
        rows.append({"discovery_alert": False, "market_gates_pass": True,
                     "trades_5m": 999, "address": "not-an-alert"})
        ranked = ranked_discovery_alerts(rows)
        self.assertEqual(len(ranked), 35)
        self.assertEqual(len(ranked[:30]), 30)
        self.assertEqual(ranked[0]["address"], "token-34")
        self.assertEqual(len({row["address"] for row in ranked}), 35)
        self.assertNotIn("not-an-alert", [row["address"] for row in ranked])

    def test_empty_and_missing_volume(self):
        self.assertEqual(ranked_discovery_alerts([]), [])
        rows = [
            {"discovery_alert": True, "market_gates_pass": False, "trades_5m": None},
            {"discovery_alert": True, "market_gates_pass": False, "trades_5m": 2},
        ]
        self.assertEqual(ranked_discovery_alerts(rows)[0]["trades_5m"], 2)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch
import brain_clean_v1 as brain


def sample(cap, ts, key="mint:pool", price=None):
    return {"key": key, "address": "mint", "pool": "pool", "symbol": "TEST",
            "cap": float(cap), "price": float(price if price is not None else cap / 100000),
            "liquidity": 15000, "volume1h": 12000, "buys5m": 16,
            "sells5m": 10, "age_seconds": 3600, "ts": ts}


class CleanPaperTests(unittest.TestCase):
    def test_new_ledger_has_100_eur_and_no_legacy(self):
        state = brain.new_state()
        self.assertEqual(state["cash"], 100)
        self.assertEqual(state["positions"], {})
        self.assertNotIn("m4", state)

    def test_staircase_requires_independent_recovery(self):
        series = [sample(c, 1000 + i * 60) for i, c in
                  enumerate([60000, 42000, 45000, 50000, 56000])]
        self.assertEqual(brain.staircase(series), (True, "staircase_confirmed"))
        self.assertFalse(brain.staircase(series[:3])[0])

    def test_entry_only_after_confirmed_pattern(self):
        state = brain.new_state()
        base = 1000
        for i, cap in enumerate([60000, 42000, 45000, 50000, 56000]):
            report = brain.step(state, [sample(cap, base + i * 60)], base + i * 60)
        self.assertEqual(report["counts"].get("paper_entry"), 1)
        self.assertEqual(state["cash"], 90)
        self.assertEqual(len(state["positions"]), 1)

    def test_unquoted_position_does_not_disappear(self):
        state = brain.new_state()
        state["positions"]["lost:pool"] = {"key": "lost:pool", "units": 2,
                                             "entry_price": 1, "cost": 2}
        report = brain.step(state, [], 2000)
        self.assertEqual(report["counts"]["position_unpriced_hold"], 1)
        self.assertIn("lost:pool", state["positions"])

    def test_low_liquidity_is_not_traded(self):
        state = brain.new_state()
        for i, cap in enumerate([60000, 42000, 45000, 50000, 56000]):
            s = sample(cap, 1000 + i * 60)
            s["liquidity"] = 100
            report = brain.step(state, [s], 1000 + i * 60)
        self.assertEqual(report["counts"]["low_liquidity"], 1)
        self.assertEqual(state["cash"], 100)

    def test_no_legacy_portfolio_import(self):
        import tempfile
        import json
        import os
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            with open(path, "w") as f:
                json.dump({"version": 10, "cash": 500}, f)
            with self.assertRaises(ValueError):
                brain.load_state(path)


if __name__ == "__main__":
    unittest.main()

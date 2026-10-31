import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import clean_v1_shadow as shadow


class ShadowLedgerSafetyTests(unittest.TestCase):
    def valid(self):
        return {"version": 1, "cash": 92.7364, "positions": {},
                "closed": [{"key": "PILLSEY"}, {"key": "iCoin"}], "history": {},
                "last_run": {"id": "41150091470", "completed_at": "2026-10-31T00:28:20Z"}}

    def test_restored_paper_baseline_preserves_losses_and_closed_trades(self):
        result = shadow.validate(self.valid())
        self.assertEqual(result["cash_eur"], 92.7364)
        self.assertEqual(result["closed_trades"], 2)

    def test_missing_or_partial_artifact_never_bootstraps_new_100(self):
        for state in ({}, {"version": 1, "cash": 100, "positions": {},
                          "closed": [], "history": {}}):
            with self.subTest(state=state), self.assertRaises(ValueError):
                shadow.validate(state)
        with tempfile.TemporaryDirectory() as d:
            with patch.object(shadow, "STATE", Path(d) / "missing.json"):
                with self.assertRaisesRegex(ValueError, "not restored"):
                    shadow.preflight()

    def test_invalid_cash_and_missing_holdings_fail_closed(self):
        for cash in (float("nan"), -1, True, "100"):
            state = self.valid()
            state["cash"] = cash
            with self.subTest(cash=cash), self.assertRaises(ValueError):
                shadow.validate(state)
        state = self.valid()
        state.pop("positions")
        with self.assertRaises(ValueError):
            shadow.validate(state)

    def test_finalize_refuses_mismatched_commit_or_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            state = self.valid()
            state["last_run"] = {"id": "shadow", "sha": "wrong"}
            (base / "state.json").write_text(json.dumps(state))
            (base / "baseline.json").write_text(json.dumps(
                {"previous_run": self.valid()["last_run"], "cash_eur": 92.7364,
                 "closed_trades": 2, "open_positions": 0}))
            (base / "report.json").write_text(json.dumps(
                {"run": {"sha": "wrong"}, "previous_run": self.valid()["last_run"]}))
            with patch.object(shadow, "STATE", base / "state.json"), \
                 patch.object(shadow, "BASELINE", base / "baseline.json"), \
                 patch.object(shadow, "COMPARISON", base / "comparison.json"), \
                 patch.object(shadow, "read_json", side_effect=lambda path: json.loads(
                     (base / ("report.json" if str(path) == "brain_clean_v1_report.json"
                              else Path(path).name)).read_text())), \
                 patch.dict(os.environ, {"CLEAN_SHADOW_HEAD_SHA": "expected"}):
                with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                    shadow.finalize()


if __name__ == "__main__":
    unittest.main()

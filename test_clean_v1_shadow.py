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

    def test_shadow_job_timeout_covers_runtime_budget(self):
        # A shadow run must have enough time to finish, finalize and upload.
        import re
        from brain_clean_v1 import RUN_BUDGET_SECONDS
        workflow = (Path(__file__).parent / ".github" / "workflows" /
                    "brain_clean_v1_shadow.yml").read_text(encoding="utf-8")
        timeout = re.search(r"(?m)^\s+timeout-minutes:\s*(\d+)\s*$", workflow)
        self.assertIsNotNone(timeout)
        self.assertGreaterEqual(int(timeout.group(1)) * 60,
                                RUN_BUDGET_SECONDS + 120)

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

    def test_finalize_includes_isolated_audit_without_realizable_value(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            prior = self.valid()["last_run"]
            state = self.valid()
            state["last_run"] = {"id": "shadow", "sha": "test-head"}
            state["isolated_positions"] = {
                "mint:pool": {"symbol": "MARVIN", "isolation_status": "UNPRICED_NOT_SOLD",
                              "isolation_reason": "user_authorized_unverifiable_exit"}}
            (base / "state.json").write_text(json.dumps(state))
            (base / "baseline.json").write_text(json.dumps(
                {"previous_run": prior, "cash_eur": 92.7364,
                 "closed_trades": 2, "open_positions": 0}))
            (base / "report.json").write_text(json.dumps(
                {"run": {"sha": "test-head"}, "previous_run": prior}))
            def reader(path):
                name = "report.json" if str(path) == "brain_clean_v1_report.json" else Path(path).name
                return json.loads((base / name).read_text())
            with patch.object(shadow, "STATE", base / "state.json"), \
                 patch.object(shadow, "BASELINE", base / "baseline.json"), \
                 patch.object(shadow, "COMPARISON", base / "comparison.json"), \
                 patch.object(shadow, "read_json", side_effect=reader), \
                 patch.dict(os.environ, {"CLEAN_SHADOW_HEAD_SHA": "test-head"}):
                shadow.finalize()
            comparison = json.loads((base / "comparison.json").read_text())
            self.assertEqual(comparison["shadow_cash_eur"], 92.7364)
            audit = comparison["isolated_position_audit"]
            self.assertEqual(audit["audit"]["coverage_pct"], 33.33)
            self.assertIsNone(audit["audit"]["positions"]["MARVIN"]["realizable_value_eur"])
            self.assertEqual(audit["records"]["MARVIN"]["route_status"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()

import copy
import tempfile
import unittest
from pathlib import Path

import brain_clean_v1 as brain
import brain_clean_v1_paper2 as paper2


class SecondPaperLedgerTests(unittest.TestCase):
    def test_independent_baseline_and_no_cross_portfolio_mutation(self):
        original = brain.new_state()
        original["cash"] = 33.9529
        original["positions"]["old:pool"] = {"key": "old:pool", "cost": 10}
        frozen = copy.deepcopy(original)
        second = paper2.seed()
        self.assertEqual(second["cash"], 100.0)
        self.assertEqual(second["positions"], {})
        self.assertEqual(second["closed"], [])
        self.assertEqual(original, frozen)
        self.assertEqual(paper2.baseline_report()["status"], "READY_NOT_RUNNING")

    def test_initialize_once_preserves_existing_cash_and_trades(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper2.json"
            first = paper2.initialize_once(path)
            self.assertEqual(first["cash"], 100.0)
            first["cash"] = 83.5
            first["closed"] = [{"key": "example", "pnl_eur": -1.5}]
            import json
            path.write_text(json.dumps(first), encoding="utf-8")
            with self.assertRaises(FileExistsError):
                paper2.initialize_once(path)
            recovered = paper2.load_existing(path)
            self.assertEqual(recovered["cash"], 83.5)
            self.assertEqual(len(recovered["closed"]), 1)

    def test_missing_ledger_fails_closed_instead_of_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                paper2.load_existing(Path(folder) / "missing.json")

    def test_rejects_other_portfolio_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            path.write_text('{"version":1,"portfolio_id":"control","cash":100}')
            with self.assertRaises(ValueError):
                paper2.load_existing(path)

    def test_corrupt_restored_cash_or_positions_fails_closed(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper2.json"
            for cash in (float("nan"), -1, "100", True):
                state = paper2.seed()
                state["cash"] = cash
                path.write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaises(ValueError):
                    paper2.load_existing(path)
            state = paper2.seed()
            state["positions"] = []
            path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaises(ValueError):
                paper2.load_existing(path)

    def test_bootstrap_rejects_expired_and_ambiguous_artifact_history(self):
        paper2.assert_never_bootstrapped({"total_count": 0, "artifacts": []})
        for listing in (
            {"total_count": 1, "artifacts": [{"expired": True}]},
            {"total_count": 1, "artifacts": []},
            {"artifacts": []},
            {"total_count": "0", "artifacts": []},
            {"total_count": 0, "artifacts": [{"expired": False}]},
        ):
            with self.subTest(listing=listing), self.assertRaises((ValueError, FileExistsError)):
                paper2.assert_never_bootstrapped(listing)

    def test_bootstrap_workflow_serializes_competing_runs(self):
        workflow = (Path(__file__).parent / ".github/workflows/brain_clean_v1_paper2_bootstrap.yml").read_text(encoding="utf-8")
        self.assertIn("concurrency:\n  group: brain-clean-v1-paper2-bootstrap\n  cancel-in-progress: false", workflow)

    def test_bootstrap_requires_explicit_dispatch(self):
        workflow = (Path(__file__).parent / ".github/workflows/brain_clean_v1_paper2_bootstrap.yml").read_text(encoding="utf-8")
        header = workflow.split("permissions:", 1)[0]
        self.assertIn("  workflow_dispatch:", header)
        self.assertNotIn("\n  push:", header)
        self.assertNotIn("\n  schedule:", header)
        # Check event keys by line, not only exact two-space indentation.
        import re
        self.assertEqual(re.findall(r"(?m)^\s{2,}(\w[\w-]*):\s*$", header), ["workflow_dispatch"])

    def test_ci_covers_paper2_ledger_runner_and_bootstrap_changes(self):
        workflow = (Path(__file__).parent / ".github/workflows/paper2_ci.yml").read_text(encoding="utf-8")
        for changed_path in (
            ".github/workflows/paper2_ci.yml",
            ".github/workflows/brain_clean_v1_paper2_bootstrap.yml",
            "brain_clean_v1_paper2.py",
            "brain_clean_v1_paper2_run.py",
            "test_brain_clean_v1_paper2.py",
        ):
            with self.subTest(path=changed_path):
                self.assertIn(f"- '{changed_path}'", workflow)

    def test_runner_rejects_duplicate_and_missing_run_ids(self):
        from brain_clean_v1_paper2_run import verify_run_identity
        verify_run_identity("123", "124")
        for source, current in (("123", "123"), ("", "124"), ("123", ""), (None, "124")):
            with self.subTest(source=source, current=current), self.assertRaises(RuntimeError):
                verify_run_identity(source, current)

    def test_observe_rejects_control_state(self):
        with self.assertRaises(ValueError):
            paper2.observe(brain.new_state(), [])


if __name__ == "__main__":
    unittest.main()

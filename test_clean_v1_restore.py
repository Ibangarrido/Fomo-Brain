import unittest
from unittest.mock import patch
import clean_v1_restore as restore


def artifact(ident, uploaded, run_id, branch="main"):
    return {"id": ident, "name": restore.NAME, "expired": False,
            "created_at": uploaded, "workflow_run": {"id": run_id, "head_branch": branch}}


class RestoreTests(unittest.TestCase):
    def test_upload_time_wins_over_misordered_run_ids(self):
        # Observed: #148 selected #145 although #147 had uploaded later.
        rows = [artifact(145, "2026-11-01T09:00:32Z", 41290468094),
                artifact(147, "2026-11-01T09:31:36Z", 41292725360),
                artifact(146, "2026-11-01T09:15:44Z", 41291541978)]
        self.assertEqual(restore.newest_artifact(rows, 41293853380)["id"], 147)
        self.assertEqual(restore.newest_artifact(list(reversed(rows)), 41293853380)["id"], 147)

    def test_ignore_current_run_expired_and_other_branches(self):
        rows = [artifact(1, "2026-11-01T09:00:00Z", 10),
                artifact(2, "2026-11-01T10:00:00Z", 20, "feature"),
                artifact(3, "2026-11-01T11:00:00Z", 30)]
        rows[-1]["expired"] = True
        self.assertEqual(restore.newest_artifact(rows, 40)["id"], 1)
        with self.assertRaises(RuntimeError):
            restore.newest_artifact(rows, 10)

    def test_cross_run_download_pins_selected_source_run(self):
        # Regression: PR shadow #18 selected a valid production artifact,
        # but download-artifact defaulted to the PR's own run ID and found none.
        from pathlib import Path
        for workflow in ("brain_clean_v1_shadow.yml", "brain_clean_v1.yml"):
            with self.subTest(workflow=workflow):
                content = (Path(__file__).parent / ".github" / "workflows" / workflow).read_text()
                download_step = content.split("uses: actions/download-artifact@v4", 1)[1]
                download_step = download_step.split("      - name:", 1)[0]
                self.assertIn("artifact-ids: ${{ steps.restore.outputs.artifact_id }}",
                              download_step)
                self.assertIn("run-id: ${{ steps.restore.outputs.source_run }}",
                              download_step)
                self.assertIn("merge-multiple: true", download_step)
                self.assertIn("github-token: ${{ github.token }}",
                              download_step)

    def test_reject_nonfinite_and_negative_cash(self):
        state = {"version": 1, "cash": 10.0, "positions": {}, "closed": [],
                 "last_run": {"id": "147"}}
        report = {"run": {"id": "147"}}
        for cash in (float("nan"), float("inf"), -1.0, True):
            with self.subTest(cash=cash), self.assertRaises(RuntimeError):
                restore.verify_ledger({**state, "cash": cash}, report, "147")

    def test_source_workflow_requires_successful_completion(self):
        from pathlib import Path
        source = (Path(__file__).parent / "clean_v1_restore.py").read_text()
        self.assertIn('run.get("conclusion") != "success"', source)

    def test_fail_closed_if_source_run_does_not_match_ledger(self):
        state = {"version": 1, "cash": 60.14, "positions": {}, "closed": [],
                 "last_run": {"id": "147"}}
        report = {"run": {"id": "147"}}
        restore.verify_ledger(state, report, "147")
        with self.assertRaises(RuntimeError):
            restore.verify_ledger(state, report, "145")
        with self.assertRaises(RuntimeError):
            restore.verify_ledger(state, {"run": {"id": "145"}}, "147")


if __name__ == "__main__":
    unittest.main()

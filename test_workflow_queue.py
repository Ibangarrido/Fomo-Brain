"""Regression checks for FOMO Brain's state-safe Actions concurrency."""
from pathlib import Path
import re
import unittest

WORKFLOW = Path(__file__).parent / ".github" / "workflows" / "fomo_brain.yml"


class WorkflowQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.header = cls.source.split("\njobs:", 1)[0]

    def test_both_dispatch_sources_remain_enabled(self):
        self.assertRegex(self.header, r"(?m)^  workflow_dispatch:\s*$")
        self.assertRegex(self.header, r"(?m)^  schedule:\s*$")
        self.assertIn('cron: "7,27,47 * * * *"', self.header)

    def test_pending_runs_are_preserved_and_active_runs_not_cancelled(self):
        self.assertRegex(self.header, r"(?m)^concurrency:\s*$")
        self.assertRegex(self.header, r"(?m)^  queue: max\s*$")
        self.assertRegex(self.header, r"(?m)^  cancel-in-progress: false\s*$")
        self.assertNotRegex(self.header, r"(?m)^  queue: single\s*$")

    def test_schedule_and_manual_share_the_same_state_lock(self):
        self.assertIn('group: fomo-brain-state-${{ github.ref }}', self.header)
        self.assertNotIn("github.event_name", self.header)

    def test_paper_entry_and_quote_guards_unchanged(self):
        self.assertIn("python brain_paper_entry.py", self.source)
        self.assertIn('BRAIN_QUOTE_GUARD: "1"', self.source)
        self.assertIn('BRAIN_UNKNOWN_ISOLATION: "1"', self.source)


if __name__ == "__main__":
    unittest.main()

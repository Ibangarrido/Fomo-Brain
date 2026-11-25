import unittest
from datetime import datetime, timezone
from copy import deepcopy
from brain_v2_sentinel import audit

class SentinelTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 25, tzinfo=timezone.utc)
        self.state = dict(portfolio_id="clean-v1-paper-2", cash=97.58,
                          closed=[{"id":"a"}], positions={}, paper2_epoch="test",
                          last_run={"id":"1","completed_at":self.now.isoformat()})
    def test_clean(self):
        self.assertEqual(audit(self.state, now=self.now)["issues"], [])
    def test_duplicate(self):
        self.state["closed"] *= 2
        self.assertIn("DUPLICATE_CLOSED_ID", audit(self.state, now=self.now)["issues"])
    def test_epoch_and_history(self):
        old = deepcopy(self.state)
        self.state.update(paper2_epoch="new", closed=[])
        issues = audit(self.state, old, self.now)["issues"]
        self.assertIn("EPOCH_CHANGED", issues)
        self.assertIn("CLOSED_HISTORY_CHANGED", issues)
    def test_stale(self):
        self.state["last_run"]["completed_at"] = "2026-11-24T00:00:00+00:00"
        self.assertIn("STALE_OR_FUTURE_RUN", audit(self.state, now=self.now)["issues"])
    def test_read_only(self):
        old = deepcopy(self.state)
        audit(self.state, now=self.now)
        self.assertEqual(old, self.state)

if __name__ == "__main__":
    unittest.main()

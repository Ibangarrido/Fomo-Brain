"""Regression test: urgent checkpoints beat the fixed 5/5 research quota."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import opportunity_audit as audit


class CheckpointPriorityTests(unittest.TestCase):
    def test_six_urgent_rejections_are_not_capped_at_five(self):
        now = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)
        first = (now - timedelta(minutes=20)).isoformat()
        rejected = (now - timedelta(minutes=5, seconds=30)).isoformat()
        rows = {}
        for i in range(6):
            address = "urgent_" + str(i)
            rows[address] = {"chain": "solana", "address": address,
                             "first": {"received_at": first},
                             "first_rejection": {"received_at": rejected},
                             "post_rejection_checkpoints": {},
                             "admission_pool": "rejected_reserve"}
        for i in range(8):
            address = "ordinary_" + str(i)
            rows[address] = {"chain": "solana", "address": address,
                             "first": {"received_at": first},
                             "admission_pool": "ordinary"}
        with patch.object(audit, "read", return_value={"tokens": rows, "watch_cursor": 0}):
            targets = audit.watch_targets(now)
        self.assertEqual(len(targets), 10 + len(audit.MANUAL))
        self.assertTrue(all(("solana", "urgent_" + str(i)) in targets for i in range(6)))

    def test_no_extra_automatic_requests(self):
        now = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)
        first = (now - timedelta(minutes=20)).isoformat()
        rejected = (now - timedelta(minutes=5, seconds=30)).isoformat()
        rows = {str(i): {"chain": "solana", "address": str(i),
                          "first": {"received_at": first},
                          "first_rejection": {"received_at": rejected},
                          "post_rejection_checkpoints": {},
                          "admission_pool": "rejected_reserve"} for i in range(15)}
        with patch.object(audit, "read", return_value={"tokens": rows, "watch_cursor": 0}):
            targets = audit.watch_targets(now)
        automatic = [t for t in targets if t not in audit.MANUAL]
        self.assertEqual(len(automatic), 10)


if __name__ == "__main__":
    unittest.main()

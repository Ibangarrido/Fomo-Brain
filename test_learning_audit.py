"""Offline regression tests for prospective rejection cohort labeling."""
import unittest
from datetime import datetime, timedelta, timezone
from learning_audit import summarize


class LearningAuditTests(unittest.TestCase):
    def test_buy_ratio_group_reads_rejection_reason_not_strategy_label(self):
        now = datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)
        t0 = (now - timedelta(hours=1)).isoformat()
        def row(reason, *, lag=60, same_pair=True, cohort="automatic_prospective"):
            return {"cohort": cohort,
                    "first_rejection": {"received_at": t0, "pair": "pool_1",
                                        "entry_rejections": {"LAB CONTINUATION 60": reason}},
                    "post_rejection_checkpoints": {"30m": {
                        "lag_seconds": lag, "pair_changed": not same_pair,
                        "sampled_up_20pct": True, "sampled_down_20pct": False}}}
        tokens = {"ratio": row("ratio compras < 60%"),
                  "other": row("continuation: edad fuera de 2-1440 min"),
                  "late": row("ratio compras < 60%", lag=300),
                  "different_pool": row("ratio compras < 60%", same_pair=False),
                  "manual": row("ratio compras < 60%", cohort="manual_after_event")}
        result = summarize(tokens, now, minimum=1)
        self.assertEqual(result["groups"]["buy_ratio"]["eligible"], 1)
        self.assertEqual(result["groups"]["other"]["eligible"], 1)
        self.assertEqual(result["excluded"]["missing_or_late"], 1)
        self.assertEqual(result["excluded"]["changed_or_unknown_pair"], 1)
        self.assertEqual(result["excluded"]["retrospective"], 1)
        self.assertEqual(result["status"], "EVIDENCE_ONLY")
        self.assertEqual(result["groups"]["buy_ratio"]["down20_rate"], 0.0)
        self.assertTrue(result["groups"]["other"]["sample_sufficient"])
        self.assertEqual(summarize(tokens, now, minimum=20)["status"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()

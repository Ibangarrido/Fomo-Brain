"""Offline regression tests: feedback is bounded, comparable and read-only."""
import copy
import unittest
from datetime import datetime, timezone

from learning_feedback import evaluate


def case(address, reason="ratio compras < 60%", *, pct=22, lag=15,
         changed=False, cohort="automatic_prospective", at="2026-10-29T12:05:15+00:00"):
    return {
        "chain": "solana", "address": address, "cohort": cohort,
        "first_rejection": {
            "received_at": "2026-10-29T12:00:00+00:00",
            "entry_rejections": {"M4": reason}},
        "post_rejection_checkpoints": {"5m": {
            "observed_at": at, "lag_seconds": lag,
            "price_change_pct": pct, "pair_changed": changed}}
    }


class LearningFeedbackTests(unittest.TestCase):
    NOW = datetime(2026, 10, 29, 13, tzinfo=timezone.utc)

    def test_valid_rejected_cohort_is_research_only(self):
        state = {"tokens": {str(i): case(str(i)) for i in range(21)}}
        before = copy.deepcopy(state)
        report = evaluate(state, self.NOW)
        self.assertEqual(state, before)
        cohort = next(c for c in report["cohorts"] if c["blocker"] == "buy_pressure")
        self.assertEqual((cohort["observations"], cohort["sampled_up_20pct"]), (21, 21))
        self.assertEqual(cohort["action"], "review_offline_only")
        self.assertFalse(report["auto_parameter_changes"])
        self.assertFalse(report["executable_fills_verified"])

    def test_excludes_manual_cross_pool_late_future_and_missing_prices(self):
        cases = {
            "manual": case("manual", cohort="manual_after_event"),
            "pool": case("pool", changed=True),
            "late": case("late", lag=121),
            "future": case("future", at="2026-10-30T12:05:15+00:00"),
            "missing": case("missing", pct=None),
            "valid": case("valid", pct=-25),
        }
        report = evaluate({"tokens": cases}, self.NOW)
        cohort = next(c for c in report["cohorts"] if c["blocker"] == "buy_pressure")
        self.assertEqual((cohort["observations"], cohort["sampled_down_20pct"]), (1, 1))
        self.assertEqual(cohort["action"], "collect_more")
        self.assertEqual(report["excluded"]["manual_after_event"], 1)
        self.assertEqual(report["excluded"]["pair_unverified_5m"], 1)
        self.assertEqual(report["excluded"]["late_5m"], 1)

    def test_stale_checkpoint_cannot_masquerade_as_timely_receipt(self):
        # A forged lag of 15 seconds cannot make a 30-minute-old quote a 5m sample.
        row = case("stale", at="2026-10-29T12:30:15+00:00", lag=15)
        report = evaluate({"tokens": {"stale": row}}, self.NOW)
        self.assertEqual(report["cohorts"], [])
        self.assertEqual(report["excluded"]["inconsistent_lag_5m"], 1)

    def test_multiple_strategy_reasons_do_not_duplicate_token_in_group(self):
        row = case("same")
        row["first_rejection"]["entry_rejections"]["V13"] = "ratio compras < 75%"
        report = evaluate({"tokens": {"one": row}}, self.NOW)
        self.assertEqual(report["cohorts"][0]["observations"], 1)

    def test_three_fresh_examples_raise_early_signal_but_never_modify_gates(self):
        state = {"tokens": {str(i): case(str(i), pct=25) for i in range(3)}}
        report = evaluate(state, self.NOW)
        cohort = next(c for c in report["cohorts"] if c["blocker"] == "buy_pressure")
        self.assertEqual(cohort["early_signal"], "possible_missed_upside")
        self.assertFalse(cohort["sufficient_for_review"])
        self.assertEqual(cohort["action"], "collect_more")
        self.assertFalse(report["auto_parameter_changes"])

    def test_early_downside_protection_and_single_example_are_not_overstated(self):
        state = {"tokens": {str(i): case(str(i), pct=-23) for i in range(3)}}
        cohort = evaluate(state, self.NOW)["cohorts"][0]
        self.assertEqual(cohort["early_signal"], "possible_downside_protection")
        one = evaluate({"tokens": {"one": case("one", pct=50)}}, self.NOW)
        self.assertEqual(one["cohorts"][0]["early_signal"], "insufficient_evidence")

    def test_unpriced_or_absent_historic_positions_are_never_valued(self):
        state = {"cash": 89.83, "reserve": 0.55,
                 "positions": [{"address": "MACCA", "price": None}],
                 "tokens": {"one": case("one")}}
        old = copy.deepcopy(state)
        evaluate(state, self.NOW)
        self.assertEqual(state, old)


if __name__ == "__main__":
    unittest.main()

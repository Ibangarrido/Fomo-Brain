import unittest
from clean_v1_artifact_audit import audit_state, audit_position

class ArtifactAuditTests(unittest.TestCase):
    def test_missing_data_never_claims_complete_or_realizable(self):
        result = audit_state({})
        self.assertEqual(result["coverage_pct"], 0)
        self.assertFalse(result["complete"])
        self.assertIsNone(result["positions"]["MARVIN"]["realizable_value_eur"])

    def test_explicit_missing_reasons_are_valid_evidence(self):
        p = {k + "_missing_reason": "UNVERIFIED" for k in
             ("quote_timestamp", "liquidity_usd", "route_status", "retention_reason")}
        self.assertTrue(audit_position(p)["complete"])

    def test_invalid_numbers_and_unverified_value(self):
        p = {"quote_timestamp": "2026-11-03T00:00:00Z",
             "liquidity_usd": float("nan"), "route_status": "UNVERIFIED",
             "retention_reason": "NO_ROUTE", "realizable_value_eur": 50}
        result = audit_position(p)
        self.assertEqual(result["missing"], ["liquidity_usd"])
        self.assertIsNone(result["realizable_value_eur"])

    def test_all_three_covered_and_verification_required_for_value(self):
        p = {"quote_timestamp": "2026-11-03T00:00:00Z", "liquidity_usd": 12000,
             "route_status": "VERIFIED", "retention_reason": "NONE",
             "realizable_value_eur": 2.5, "execution_verified": True}
        result = audit_state({name: p for name in ("MARVIN", "REGRET", "paws")})
        self.assertTrue(result["complete"])
        self.assertEqual(result["coverage_pct"], 100)
        self.assertEqual(result["positions"]["paws"]["realizable_value_eur"], 2.5)

    def test_ledger_normalization_keeps_unverified_exit_unknown(self):
        from clean_v1_artifact_audit import audit_isolated_ledger
        state = {"isolated_positions": {
            "mint:pool": {"symbol": "MARVIN", "isolation_status": "UNPRICED_NOT_SOLD",
                          "isolation_reason": "user_authorized_unverifiable_exit",
                          "monitoring_audit": {"quote_status": "MISSING_OR_INVALID"}}}}
        result = audit_isolated_ledger(state)
        self.assertEqual(result["audit"]["coverage_pct"], 33.33)
        self.assertIsNone(result["records"]["MARVIN"]["quote_timestamp"])
        self.assertEqual(result["records"]["MARVIN"]["route_status"], "UNVERIFIED")
        self.assertIsNone(result["audit"]["positions"]["MARVIN"]["realizable_value_eur"])
        self.assertEqual(result["audit"]["positions"]["REGRET"]["missing"],
                         ["quote_timestamp", "liquidity_usd", "route_status", "retention_reason"])

    def test_retained_quote_is_not_presented_as_fresh_or_executable(self):
        from clean_v1_artifact_audit import audit_isolated_ledger
        state = {"isolated_positions": {"mint:pool": {
            "symbol": "paws", "isolation_reason": "NO_VERIFIED_EXIT",
            "monitoring_audit": {"last_observed_ts": 1700000000,
                                 "quote_status": "MISSING_OR_INVALID",
                                 "price_usd": 0.01, "liquidity_usd": 2500}}}}
        row = audit_isolated_ledger(state)["records"]["paws"]
        self.assertEqual(row["freshness"], "STALE_OR_UNVERIFIED")
        self.assertFalse(row["price_is_executable"])
        self.assertIsNone(row["realizable_value_eur"])
        self.assertGreater(row["quote_age_seconds"], 120)

    def test_extreme_timestamp_does_not_crash_audit(self):
        from clean_v1_artifact_audit import audit_isolated_ledger
        state = {"isolated_positions": {"mint:pool": {
            "symbol": "MARVIN",
            "monitoring_audit": {"last_observed_ts": 10**99}}}}
        row = audit_isolated_ledger(state)["records"]["MARVIN"]
        self.assertIsNone(row["quote_timestamp"])
        self.assertEqual(row["freshness"], "STALE_OR_UNVERIFIED")

if __name__ == "__main__":
    unittest.main()

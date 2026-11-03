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

if __name__ == "__main__":
    unittest.main()

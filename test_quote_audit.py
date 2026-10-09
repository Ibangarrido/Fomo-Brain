import json
import os
import tempfile
import unittest
from unittest.mock import patch

from route_shadow import QuoteAudit, fee_evidence, jupiter_pair_quote, USDC


class QuoteAuditTests(unittest.TestCase):
    def test_missing_malformed_and_zero_fees_are_distinct(self):
        for value in (None, -1, True, "0", float("nan")):
            evidence = fee_evidence({"signatureFeeLamports": value})
            self.assertIsNone(evidence["provider_network_fee_lamports"]["signatureFeeLamports"])
            self.assertEqual(evidence["cost_status"], "NETWORK_COST_UNKNOWN")
        evidence = fee_evidence({"signatureFeeLamports": 0,
                                "prioritizationFeeLamports": 0, "rentFeeLamports": 0})
        self.assertEqual(evidence["missing_network_fee_fields"], [])
        self.assertEqual(evidence["cost_status"], "PROVIDER_ESTIMATE_ONLY")
        self.assertIsNone(evidence["net_liquidation_value_usdc"])
        self.assertFalse(evidence["execution_verified"])

    def test_declared_fees_do_not_change_gross_quote_or_create_net_value(self):
        mint = "HciAVS1urBtboqhLe59HWiMeeN2McEd6y8h4HGkrpump"
        data = {"inputMint": mint, "outputMint": USDC, "inAmount": "123",
                "swapMode": "ExactIn", "transaction": None, "router": "metis",
                "outAmount": "109810", "otherAmountThreshold": "109810",
                "signatureFeeLamports": 5000, "feeBps": 10}
        record = jupiter_pair_quote(mint, USDC, "123", lambda url: data)
        self.assertEqual(record["output_amount_raw"], "109810")
        self.assertEqual(record["fee_evidence"]["provider_fee_bps"], 10)
        self.assertIsNone(record["fee_evidence"]["net_liquidation_value_usdc"])

    def test_new_session_replaces_old_marks_and_preserves_wallet_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            audit_path = os.path.join(directory, "audit.json")
            wallet = os.path.join(directory, "fomo_paper.json")
            with open(wallet, "wb") as handle:
                handle.write(b'{"cash":100}')
            old = QuoteAudit(audit_path)
            old.save("JUPITER", {"status": "QUOTE_ONLY", "expected_out_usdc": 6})
            fresh = QuoteAudit(audit_path)
            fresh.save()
            fresh.save("JUPITER", {"status": "UNAVAILABLE"})
            with open(audit_path) as handle:
                saved = json.load(handle)
            self.assertEqual(saved["records"], [{"kind": "JUPITER", "status": "UNAVAILABLE"}])
            with open(wallet, "rb") as handle:
                self.assertEqual(handle.read(), b'{"cash":100}')

    def test_bounded_history_reports_dropped_records_and_run_identity(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"GITHUB_RUN_ID": "496"}):
            audit = QuoteAudit(os.path.join(directory, "audit.json"))
            for index in range(302):
                audit.save("JUPITER", {"index": index})
            with open(audit.path) as handle:
                saved = json.load(handle)
            self.assertEqual(saved["run_id"], "496")
            self.assertEqual(len(saved["records"]), 300)
            self.assertEqual(saved["dropped_records"], 2)
            self.assertEqual(saved["records"][0]["index"], 2)

    def test_storage_failure_does_not_stop_observation(self):
        audit = QuoteAudit("/missing-parent/audit.json")
        with patch("builtins.print") as output:
            audit.save("JUPITER", {"status": "UNAVAILABLE"})
        output.assert_called_once()


if __name__ == "__main__":
    unittest.main()

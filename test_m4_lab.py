import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import fomo_brain as brain
import m4_lab as lab
from test_fomo_v8 import pair


class M4Tests(unittest.TestCase):
    def test_raydium_fallback_reports_actual_source_without_changing_accounting(self):
        now = datetime.now(timezone.utc)
        before = copy.deepcopy(self.seed)
        record = self.diagnostic_record(now, kind="RAYDIUM",
            provider="Raydium Trade API", threshold_usdc=.105)
        result = lab.m4_diagnostic(self.seed, {"records": [record]}, now)
        self.assertEqual(result["gross_quote_usdc"], .108)
        self.assertIn("Raydium", result["reference_source"])
        self.assertEqual(result["quoted_threshold_usdc"], .105)
        self.assertEqual(len(result["missing_network_fee_fields"]), 3)
        self.assertFalse(result["threshold_is_guaranteed"])
        self.assertIsNone(result["net_value_usdc"])
        self.assertEqual(self.seed, before)

    def test_raydium_receipt_expires_after_30_seconds_without_changing_balances(self):
        now = datetime.now(timezone.utc)
        before = copy.deepcopy(self.seed)
        ray = self.diagnostic_record(now, kind="RAYDIUM")
        for age, valid in ((30, True), (31, False)):
            result = lab.m4_diagnostic(self.seed, {"records": [ray]},
                                       now + timedelta(seconds=age))
            self.assertEqual(result["gross_quote_usdc"] is not None, valid)
            self.assertEqual(result["provider_diagnostics"]["RAYDIUM"]
                             ["evidence_current"], valid)
        self.assertEqual(self.seed, before)

    def test_expired_raydium_does_not_hide_valid_jupiter_reference(self):
        now = datetime.now(timezone.utc)
        ray = self.diagnostic_record(now - timedelta(seconds=31), kind="RAYDIUM",
                                     expected_out_usdc=.2)
        jup = self.diagnostic_record(now - timedelta(seconds=60))
        result = lab.m4_diagnostic(self.seed, {"records": [ray, jup]}, now)
        self.assertEqual(result["gross_quote_usdc"], .108)
        self.assertEqual(result["recent_quote_providers"], ["JUPITER"])
        self.assertEqual(result["quote_receipt_ttl_seconds"], 120)
        self.assertIsNone(result["net_value_usdc"])

    def test_complete_provider_fee_fields_still_require_conversion_and_execution(self):
        now = datetime.now(timezone.utc)
        record = self.diagnostic_record(now, fee_evidence={
            "provider_network_fee_lamports": {
                "signatureFeeLamports": 5000, "prioritizationFeeLamports": 0,
                "rentFeeLamports": 0}})
        result = lab.m4_diagnostic(self.seed, {"records": [record]}, now)
        self.assertEqual(result["missing_network_fee_fields"], [])
        self.assertIn("NETWORK_FEE_CONVERSION_UNVERIFIED", result["net_value_blockers"])
        self.assertIsNone(result["net_value_usdc"])

    def test_zero_fees_without_wallet_cannot_certify_free_m4_exit(self):
        now = datetime.now(timezone.utc)
        record = self.diagnostic_record(now, threshold_usdc=.105, fee_evidence={
            "provider_network_fee_lamports": {
                "signatureFeeLamports": 0, "prioritizationFeeLamports": 0,
                "rentFeeLamports": 0}, "wallet_context_present": False})
        before = copy.deepcopy(self.seed)
        result = lab.m4_diagnostic(self.seed, {"records": [record]}, now)
        self.assertIn("WALLET_CONTEXT_MISSING", result["net_value_blockers"])
        self.assertFalse(result["wallet_costs_verified"])
        self.assertEqual(result["cost_ceiling_usdc_for_positive_proceeds"], .108)
        self.assertEqual(result["threshold_cost_ceiling_usdc"], .105)
        self.assertIsNone(result["net_value_usdc"])
        self.assertEqual(self.seed, before)

    def test_bad_threshold_cannot_be_reported_as_minimum_proceeds(self):
        now = datetime.now(timezone.utc)
        for value in (True, -.1, .109, float("nan")):
            result = lab.m4_diagnostic(self.seed, {"records": [
                self.diagnostic_record(now, threshold_usdc=value)]}, now)
            self.assertIsNone(result["quoted_threshold_usdc"])

    def test_latest_valid_source_wins_and_expired_raydium_is_rejected(self):
        now = datetime.now(timezone.utc)
        ray = self.diagnostic_record(now, kind="RAYDIUM", expected_out_usdc=.11)
        jup = self.diagnostic_record(now-timedelta(seconds=10))
        self.assertEqual(lab.m4_diagnostic(self.seed, {"records":[ray, jup]}, now)
                         ["gross_quote_usdc"], .11)
        self.assertIsNone(lab.m4_diagnostic(self.seed, {"records":[ray]},
                         now+timedelta(seconds=121))["gross_quote_usdc"])

    def test_failure_categories_do_not_confuse_api_failure_with_liquidity(self):
        for record, expected in (({'http_status':429}, 'RATE_LIMIT'),
                                 ({'http_status':403}, 'AUTH_OR_ACCESS'),
                                 ({'http_status':503,'error':'no route found'}, 'PROVIDER_FAILURE'),
                                 ({'error':'TimeoutError: timed out'}, 'TIMEOUT'),
                                 ({'provider_error':{'error':'COULD_NOT_FIND_ANY_ROUTE'}}, 'NO_ROUTE_REPORTED'),
                                 ({'error':'bad response'}, 'UNCLASSIFIED_FAILURE')):
            self.assertEqual(lab.quote_failure(record), expected)

    def test_latest_failure_is_reported_separately_from_older_gross_quote(self):
        now = datetime.now(timezone.utc)
        failure = dict(self.diagnostic_record(now), status='UNAVAILABLE', http_status=429)
        audit = {'records':[failure, self.diagnostic_record(now-timedelta(seconds=10))]}
        before = copy.deepcopy(self.seed)
        result = lab.m4_diagnostic(self.seed, audit, now)
        self.assertEqual(result['latest_attempt']['diagnosis'], 'RATE_LIMIT')
        self.assertEqual(result['gross_quote_usdc'], .108)
        stale = lab.m4_diagnostic(self.seed, audit, now+timedelta(seconds=121))
        self.assertFalse(stale['latest_attempt']['evidence_current'])
        self.assertIsNone(stale['gross_quote_usdc'])
        self.assertEqual(self.seed, before)

    def test_raydium_no_route_does_not_hide_jupiter_quantity_quote(self):
        now = datetime.now(timezone.utc)
        ray = dict(self.diagnostic_record(now, kind='RAYDIUM'),
                   status='UNAVAILABLE', provider_message='ROUTE_NOT_FOUND')
        jup = self.diagnostic_record(now-timedelta(seconds=10))
        before = copy.deepcopy(self.seed)
        result = lab.m4_diagnostic(self.seed, {'records': [jup, ray]}, now)
        self.assertEqual(result['provider_diagnostics']['RAYDIUM']['diagnosis'],
                         'NO_ROUTE_REPORTED')
        self.assertEqual(result['provider_diagnostics']['JUPITER']['status'], 'QUOTE_ONLY')
        self.assertEqual(result['recent_quote_providers'], ['JUPITER'])
        self.assertEqual(result['gross_quote_usdc'], .108)
        self.assertEqual(result['next_check'],
                         'VERIFY_WALLET_SPECIFIC_COSTS_AND_FX_BEFORE_NET_VALUATION')
        self.assertIsNone(result['net_value_usdc'])
        self.assertEqual(self.seed, before)

    def test_provider_failures_and_expired_quotes_leave_value_unknown(self):
        now = datetime.now(timezone.utc)
        records = [self.diagnostic_record(now-timedelta(seconds=121)),
                   dict(self.diagnostic_record(now, kind='RAYDIUM'),
                        status='UNAVAILABLE', http_status=503,
                        provider_message='ROUTE_NOT_FOUND')]
        result = lab.m4_diagnostic(self.seed, {'records': records}, now)
        self.assertEqual(result['provider_diagnostics']['RAYDIUM']['diagnosis'],
                         'PROVIDER_FAILURE')
        self.assertFalse(result['provider_diagnostics']['JUPITER']['evidence_current'])
        self.assertEqual(result['recent_quote_providers'], [])
        self.assertIsNone(result['gross_quote_usdc'])

    def test_route_failure_classification_preserves_http_precedence(self):
        self.assertEqual(lab.quote_failure({'provider_message': 'ROUTE_NOT_FOUND'}),
                         'NO_ROUTE_REPORTED')
        self.assertEqual(lab.quote_failure({'provider_message': 'Insufficient liquidity'}),
                         'INSUFFICIENT_LIQUIDITY_REPORTED')
        self.assertEqual(lab.quote_failure({'http_status': 429,
                                           'provider_message': 'ROUTE_NOT_FOUND'}), 'RATE_LIMIT')
        self.assertEqual(lab.quote_failure({'http_status': 400}), 'UNCLASSIFIED_FAILURE')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = os.getcwd()
        os.chdir(self.temp.name)
        self.seed = {"version": 1, "cash": 82.0, "reserve": 10.0,
                     "positions": [{"chain": "solana", "address": lab.MINT,
                                    "symbol": "M4", "pair": "pool", "quantity": 100,
                                    "budget": 5.0, "mark_net": 6.49,
                                    "quote_status": "NO VERIFICABLE",
                                    "opened_at": "2026-10-06T23:11:00+00:00",
                                    "last_quote_at": "2026-10-06T23:32:00+00:00"}],
                     "closed": [], "seen": ["solana:" + lab.MINT], "observations": []}
        lab.write(lab.SOURCE, self.seed)

    def tearDown(self):
        os.chdir(self.previous)
        self.temp.cleanup()

    def read(self, path):
        with open(path) as handle:
            return json.load(handle)

    def diagnostic_record(self, now, **changes):
        return dict({"kind": "JUPITER", "chain": "solana", "address": lab.MINT,
                     "quantity": 100, "status": "QUOTE_ONLY", "expected_out_usdc": .108,
                     "output_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                     "received_at": now.isoformat()}, **changes)

    def test_recent_quote_does_not_revalue_sell_or_convert_currency(self):
        now = datetime.now(timezone.utc)
        original = copy.deepcopy(self.seed)
        result = lab.m4_diagnostic(self.seed, {"records": [self.diagnostic_record(now)]}, now)
        self.assertEqual(result["gross_quote_usdc"], .108)
        self.assertIsNone(result["net_value_usdc"])
        self.assertFalse(result["historical_mark_is_current"])
        self.assertFalse(result["execution_verified"])
        self.assertEqual(self.seed, original)

    def test_stale_future_wrong_mint_and_wrong_quantity_quotes_are_rejected(self):
        now = datetime.now(timezone.utc)
        for changes in ({"received_at": (now-timedelta(seconds=121)).isoformat()},
                        {"received_at": (now+timedelta(seconds=1)).isoformat()},
                        {"address": "other"}, {"quantity": 101},
                        {"output_mint": "other"},
                        {"expected_out_usdc": float('nan')}, {"expected_out_usdc": True},
                        {"received_at": "2026-10-09T19:00:00"}):
            with self.subTest(changes=changes):
                result = lab.m4_diagnostic(self.seed, {"records": [self.diagnostic_record(now, **changes)]}, now)
                self.assertIsNone(result["gross_quote_usdc"])

    def test_latest_received_quote_wins_over_record_order(self):
        now = datetime.now(timezone.utc)
        audit = {"records": [self.diagnostic_record(now, expected_out_usdc=.12),
                             self.diagnostic_record(now-timedelta(seconds=20))]}
        self.assertEqual(lab.m4_diagnostic(self.seed, audit, now)["gross_quote_usdc"], .12)

    def test_reference_reports_exact_quantity_and_expires_without_fabricating_cash(self):
        now = datetime.now(timezone.utc)
        with open("fomo_quote_audit.json", "w") as handle:
            json.dump({"records": [self.diagnostic_record(now)]}, handle)
        original = copy.deepcopy(self.seed)
        reference = lab.refresh_reference(self.seed, now)
        self.assertEqual(reference["gross_value_usdc"], .108)
        self.assertAlmostEqual(reference["price_usdc"], .00108)
        self.assertIsNone(reference["net_value_usdc"])
        self.assertIsNone(reference["eur_value"])
        self.assertFalse(reference["execution_verified"])
        for field in original:
            self.assertEqual(self.seed[field], original[field])
        expired = lab.refresh_reference(self.seed, now + timedelta(seconds=121))
        self.assertIsNone(expired["gross_value_usdc"])
        self.assertEqual(self.seed["positions"][0]["mark_net"], 6.49)

    def test_simulation_persists_reference_and_keeps_unknown_risk_pause(self):
        now = datetime.now(timezone.utc)
        with open("fomo_quote_audit.json", "w") as handle:
            json.dump({"records": [self.diagnostic_record(now)]}, handle)
        lab.bootstrap()
        output = io.StringIO()
        with patch.object(brain, "cotizar_posicion", side_effect=ValueError("No quote")), \
                contextlib.redirect_stdout(output):
            brain.simular_cartera([], lab.CONTROL)
        state = self.read(lab.CONTROL)
        reference = state["observations"][-1]["m4_reference_valuation"]
        self.assertEqual(reference["gross_value_usdc"], .108)
        self.assertEqual(state["cash"], 82)
        self.assertEqual(state["reserve"], 10)
        self.assertEqual(state["closed"], [])
        self.assertIsNone(state["observations"][-1]["estimated_equity"])
        self.assertTrue(any("ENTRADAS PAUSADAS" in n for n in state["last_run_notes"]))
        self.assertIn("bruto USDC 0.108000", output.getvalue())
        self.assertIn("NO es valor actual", output.getvalue())

    def test_verified_or_absent_m4_removes_old_fallback_reference(self):
        self.seed["m4_reference_valuation"] = {"gross_value_usdc": 1}
        self.seed["positions"][0]["quote_status"] = "OK"
        self.assertIsNone(lab.refresh_reference(self.seed))
        self.assertNotIn("m4_reference_valuation", self.seed)

    def test_missing_audit_retains_unknown_value(self):
        result = lab.m4_diagnostic(self.seed)
        self.assertEqual(result["status"], "NO_RECENT_QUANTITY_QUOTE")
        self.assertIsNone(result["net_value_usdc"])

    def test_persisted_report_preserves_all_existing_state(self):
        lab.bootstrap()
        before = self.read(lab.RECOVERY)
        result = lab.report_snapshot(lab.RECOVERY)
        saved = self.read(lab.RECOVERY)
        self.assertEqual(result, saved)
        self.assertIn("last_m4_diagnostic", saved)
        del saved["last_m4_diagnostic"]
        self.assertEqual(saved, before)

    def test_malformed_audit_cannot_break_report_and_recovered_mark_is_labelled(self):
        for audit in ({"records": None}, {"records": {}}, {"records": [None, {}]}):
            self.assertIsNone(lab.m4_diagnostic(self.seed, audit)["gross_quote_usdc"])
        state = copy.deepcopy(self.seed)
        state["positions"][0]["quote_status"] = "OK"
        result = lab.m4_diagnostic(state, {"records": []})
        self.assertTrue(result["historical_mark_is_current"])
        self.assertIsNone(result["market_blocker"])

    def test_fork_preserves_every_balance_position_and_history_once(self):
        original = self.read(lab.SOURCE)
        self.assertTrue(lab.bootstrap())
        self.assertFalse(lab.bootstrap())
        for path in (lab.CONTROL, lab.RECOVERY):
            state = self.read(path)
            for field in ("cash", "reserve", "closed", "seen"):
                self.assertEqual(state[field], original[field])
            self.assertEqual(state["positions"][0]["mark_net"], 6.49)
            self.assertEqual(state["positions"][0]["quantity"], 100)
            self.assertIsNone(state["m4_baseline"]["total_equity"])
        self.assertEqual(self.read(lab.SOURCE), original)
        self.assertTrue(lab.is_quarantined(self.read(lab.RECOVERY)["positions"][0]))
        self.assertFalse(lab.is_quarantined(self.read(lab.CONTROL)["positions"][0]))

    def test_missing_arm_never_resets_capital(self):
        lab.bootstrap()
        os.remove(lab.RECOVERY)
        with self.assertRaises(ValueError):
            lab.bootstrap()

    def test_unknown_zero_for_risk_does_not_become_a_sale(self):
        state = copy.deepcopy(self.seed)
        state["cash"] = 60
        reason = brain.freno_cartera_v10(state, datetime.now(timezone.utc), conservative_unknown=True)
        self.assertIn("70.00", reason)
        self.assertEqual(state["positions"], self.seed["positions"])
        self.assertEqual(state["closed"], [])

    def test_quarantine_cannot_be_enabled_on_original_wallet(self):
        with self.assertRaises(ValueError):
            brain.simular_cartera([], lab.SOURCE, quarantine_m4=True)

    def test_recovery_buys_from_existing_cash_control_stays_paused(self):
        lab.bootstrap()
        market = pair(address="new-token", pool="new-pool")
        token = brain.analizar_par(market)
        previous = dict(token, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                        price=.95, vol5m=3000)
        def quote(position):
            if position["address"] == lab.MINT:
                raise ValueError("M4 unavailable")
            return 1, 20000, market
        for path, recovery in ((lab.CONTROL, False), (lab.RECOVERY, True)):
            with patch.object(brain, "cotizar_posicion", side_effect=quote), \
                    patch.object(brain, "cargar_memoria", return_value=[previous]), \
                    contextlib.redirect_stdout(io.StringIO()):
                brain.simular_cartera([token], path, confirm=True, quarantine_m4=recovery)
        control, recovery = self.read(lab.CONTROL), self.read(lab.RECOVERY)
        self.assertEqual(control["cash"], 82)
        self.assertEqual(len(control["positions"]), 1)
        self.assertEqual(recovery["cash"], 77)
        self.assertEqual(recovery["reserve"], 10)
        self.assertEqual(len(recovery["positions"]), 2)
        self.assertEqual(recovery["positions"][0]["mark_net"], 6.49)
        self.assertEqual(recovery["closed"], [])
        self.assertIsNone(recovery["observations"][-1]["estimated_equity"])

    def test_only_inherited_exact_contract_bypasses_pause_and_net_stays_unknown(self):
        lab.bootstrap()
        for path, recovery in ((lab.CONTROL, False), (lab.RECOVERY, True)):
            with patch.object(brain, "cotizar_posicion", side_effect=ValueError("No quote")), \
                    contextlib.redirect_stdout(io.StringIO()):
                brain.simular_cartera([], path, quarantine_m4=recovery)
            state = self.read(path)
            self.assertEqual(state["cash"], 82)
            self.assertEqual(state["reserve"], 10)
            self.assertEqual(len(state["positions"]), 1)
            self.assertEqual(state["closed"], [])
            self.assertIsNone(state["observations"][-1]["estimated_equity"])
            self.assertFalse(state["observations"][-1]["valuation_complete"])
            paused = any("ENTRADAS PAUSADAS" in note for note in state["last_run_notes"])
            self.assertEqual(paused, not recovery)
        state = self.read(lab.RECOVERY)
        unknown = dict(state["positions"][0], address="another-token")
        state["positions"].append(unknown)
        lab.write(lab.RECOVERY, state)
        with patch.object(brain, "cotizar_posicion", side_effect=ValueError("No quote")), \
                contextlib.redirect_stdout(io.StringIO()):
            brain.simular_cartera([], lab.RECOVERY, quarantine_m4=True)
        self.assertTrue(any("ENTRADAS PAUSADAS" in note
                            for note in self.read(lab.RECOVERY)["last_run_notes"]))


if __name__ == "__main__":
    unittest.main()







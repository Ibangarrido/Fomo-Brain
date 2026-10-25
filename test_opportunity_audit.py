import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import opportunity_audit as audit
from test_fomo_v8 import pair


class OpportunityTests(unittest.TestCase):
    def test_entry_summary_separates_risk_rejections_omissions_and_entries(self):
        summary = audit.entry_summary(4, [
            'DESCARTE solana:a | cartera sin valoracion completa',
            'DESCARTE solana:b | cartera sin valoracion completa',
            'ENTRADA OMITIDA solana:c: quote unavailable',
            'ENTRADA VIRTUAL TEST | EUR 5.00',
            'SALIDA VIRTUAL OLD | STOP -15%',
            'M4: sin par verificable'])
        self.assertEqual((summary['entered'], summary['rejected'], summary['omitted']), (1, 2, 1))
        self.assertEqual(summary['top_first_blockers'], {'cartera sin valoracion completa': 2})
        self.assertEqual(audit.entry_summary(0, [])['candidates'], 0)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.temp.name)
        audit.begin_cycle()
        self.now = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)

    def tearDown(self):
        os.chdir(self.old)
        self.temp.cleanup()

    def observe(self, markets, now=None):
        with contextlib.redirect_stdout(io.StringIO()):
            audit.observe({str(i): p for i, p in enumerate(markets)}, {}, now or self.now)
        return audit.read()["tokens"]

    def test_keeps_baseline_peak_drawdown_and_wallet_reasons(self):
        audit.record_decisions("CONTROL", ["DESCARTE solana:a | cartera sin valoracion completa"])
        audit.record_decisions("VELAS", ["DESCARTE solana:a | ratio compras < 60%"])
        first = self.observe([pair(price=1)])["solana:a"]["first"]
        self.observe([pair(price=3)], self.now + timedelta(hours=1))
        row = self.observe([pair(price=1.5)], self.now + timedelta(hours=2))["solana:a"]
        self.assertEqual(row["first"], first)
        self.assertEqual(row["observed_price_change_pct"], 50)
        self.assertEqual(row["observed_peak_change_pct"], 200)
        self.assertEqual(row["observed_drawdown_from_peak_pct"], -50)
        self.assertEqual(len(first["entry_rejections"]), 2)
        self.assertFalse(first["execution_verified"])
        self.assertNotIn("profit", row)

    def test_market_screens_expose_simultaneous_failures_and_missing_data(self):
        market = pair()
        market["pairCreatedAt"] = int((self.now - timedelta(hours=3)).timestamp() * 1000)
        market["txns"] = {"m5": {"buys": 25, "sells": 25}}
        market["priceChange"] = {"m5": -3}
        row = self.observe([market])["solana:a"]["last"]
        control, extended = row["early_market_screens"]["60"], row["early_market_screens"]["1440"]
        self.assertEqual(control["pair_age_2_60"], "FAIL")
        self.assertEqual(extended["pair_age_2_1440"], "PASS")
        self.assertEqual(extended["buy_count_60pct"], "FAIL")
        self.assertEqual(extended["momentum5m_2_60"], "FAIL")
        self.assertEqual(extended["change1h_max150"], "UNKNOWN")
        self.assertEqual(row["trades5m"], 50)

    def test_missing_invalid_quotes_preserve_last_price_and_report_gaps(self):
        self.observe([pair()])
        bad = pair(price="nan")
        row = self.observe([bad], self.now + timedelta(hours=1))["solana:a"]
        self.assertEqual(row["last"]["price"], 1)
        row = self.observe([pair(price=.5, pool="new")], self.now + timedelta(hours=2))["solana:a"]
        self.assertEqual(row["pair_changes"], 1)
        self.assertEqual(row["max_observation_gap_seconds"], 7200)
        self.assertEqual(row["observed_price_change_pct"], -50)

    def test_manual_winner_is_separate_from_automatic_cohort(self):
        chain, mint = next(iter(audit.MANUAL))
        market = pair(address=mint, liquidity=1)
        market["chainId"] = chain
        rows = self.observe([market, pair(address="loser")])
        self.assertEqual(rows[chain + ":" + mint]["cohort"], "manual_after_event")
        self.assertEqual(rows["solana:loser"]["cohort"], "automatic_prospective")
        self.assertIn((chain, mint), audit.watch_targets(self.now))

    def test_same_contract_different_chains_never_merge_and_liquid_pool_wins(self):
        other = pair(price=7)
        other["chainId"] = "bsc"
        rows = self.observe([pair(price=1, liquidity=20000), pair(price=10, liquidity=10000), other])
        self.assertEqual(rows["solana:a"]["last"]["price"], 1)
        self.assertEqual(rows["bsc:a"]["last"]["price"], 7)

    def test_bound_and_corrupt_state_never_silently_reset(self):
        with patch.object(audit, "LIMIT", 1):
            self.observe([pair(address="a"), pair(address="b")])
        self.assertEqual(len(audit.read()["tokens"]), 1)
        self.assertEqual(audit.read()["capacity_skips"], 1)
        with open(audit.FILE, "w") as handle:
            handle.write("broken")
        with self.assertRaises(json.JSONDecodeError):
            audit.read()

    def test_saturated_cohort_reserves_slots_for_rejected_and_manual_cases(self):
        with patch.object(audit, "LIMIT", 1), patch.object(audit, "REJECTED_RESERVE", 1):
            self.observe([pair(address="ordinary")])
            audit.record_decisions("EARLY", ["DESCARTE solana:blocked | capital brake"])
            rows = self.observe([pair(address="blocked")])
            self.assertEqual(rows["solana:blocked"]["cohort"], "automatic_rejected_overflow")
            first = rows["solana:blocked"]["first"]
            chain, mint = sorted(audit.MANUAL)[0]
            market = pair(address=mint); market["chainId"] = chain
            rows = self.observe([market])
            self.assertIn(chain + ":" + mint, rows)
            audit.record_decisions("EARLY", ["DESCARTE solana:blocked2 | capital brake"])
            rows = self.observe([pair(address="blocked2")])
            self.assertNotIn("solana:blocked2", rows)
            self.assertEqual(rows["solana:blocked"]["first"], first)
            self.assertEqual(audit.read()["capacity_skips_by_pool"], {"rejected_reserve": 1})
            self.assertEqual(len(rows), 3)

    def test_rejected_watch_rotation_keeps_both_cohorts_within_ten_requests(self):
        with patch.object(audit, "LIMIT", 10):
            self.observe([pair(address="normal" + str(i)) for i in range(10)])
            audit.record_decisions("EARLY", ["DESCARTE solana:blocked" + str(i) + " | capital brake" for i in range(10)])
            self.observe([pair(address="blocked" + str(i)) for i in range(10)])
        targets = set(audit.watch_targets(self.now)) - audit.MANUAL
        self.assertEqual(len(targets), 10)
        self.assertEqual(sum(a.startswith("blocked") for c, a in targets), 5)
        self.assertEqual(sum(a.startswith("normal") for c, a in targets), 5)

    def test_cached_receipt_does_not_create_new_baseline_peak_or_horizon(self):
        market = pair(price=1)
        market["_brain_received_at"] = self.now.isoformat()
        self.observe([market])
        market["priceUsd"] = "10"  # Even a changed payload cannot reuse old receipt.
        row = self.observe([market], self.now + timedelta(hours=73))["solana:a"]
        self.assertEqual(row["observations"], 1)
        self.assertEqual(row["last"]["price"], 1)
        self.assertNotIn("complete", row)
        market["_brain_received_at"] = (self.now + timedelta(hours=73)).isoformat()
        row = self.observe([market], self.now + timedelta(hours=73))["solana:a"]
        self.assertTrue(row["complete"])
        self.assertEqual(row["peak"]["price"], 10)

    def test_coverage_distinguishes_cached_receipts_and_late_checkpoints(self):
        audit.record_decisions("CONTROL", ["DESCARTE solana:a | cartera sin valoracion completa"])
        market = pair(price=1)
        market["_brain_received_at"] = self.now.isoformat()
        self.observe([market])
        self.observe([market], self.now + timedelta(minutes=6))
        coverage = audit.read()["last_cycle_coverage"]
        self.assertEqual(coverage["fresh_observations_accepted"], 0)
        self.assertEqual(coverage["cached_or_replayed_receipts"], 1)
        self.assertEqual(coverage["checkpoint_coverage"]["5m"]["missing"], 1)
        market["_brain_received_at"] = (self.now + timedelta(minutes=8)).isoformat()
        self.observe([market], self.now + timedelta(minutes=8))
        coverage = audit.read()["last_cycle_coverage"]
        self.assertEqual(coverage["fresh_observations_accepted"], 1)
        self.assertEqual(coverage["checkpoint_coverage"]["5m"]["late_over_120s"], 1)
        self.assertEqual(coverage["checkpoint_coverage"]["15m"]["not_due"], 1)
        market["_brain_received_at"] = (self.now + timedelta(minutes=16)).isoformat()
        self.observe([market], self.now + timedelta(minutes=16))
        coverage = audit.read()["last_cycle_coverage"]
        self.assertEqual(coverage["checkpoint_coverage"]["15m"]["on_time_within_120s"], 1)
        self.assertEqual(coverage["checkpoint_coverage"]["5m"]["late_over_120s"], 1)

    def test_receipt_time_is_distinct_from_evaluation_and_invalid_receipts_skip(self):
        market = pair()
        market["_brain_received_at"] = (self.now - timedelta(seconds=45)).isoformat()
        row = self.observe([market])["solana:a"]
        self.assertEqual(row["first"]["received_at"], market["_brain_received_at"])
        self.assertEqual(row["first"]["evaluated_at"], self.now.isoformat())
        for stamp in ("broken", "2026-10-09T12:00:00", (self.now + timedelta(seconds=1)).isoformat()):
            market["_brain_received_at"] = stamp
            self.observe([market])
        self.assertEqual(audit.read()["invalid_receipt_skips"], 3)
        self.assertEqual(audit.read()["tokens"]["solana:a"]["observations"], 1)

    def test_horizon_freezes_without_claiming_exact_final_quote(self):
        self.observe([pair()])
        row = self.observe([pair(price=2)], self.now + timedelta(hours=73))["solana:a"]
        self.assertTrue(row["complete"])
        self.assertNotIn(("solana", "a"), audit.watch_targets(self.now + timedelta(hours=74)))
        last = row["last"]
        rows = self.observe([pair(price=5)], self.now + timedelta(hours=74))
        self.assertNotIn('solana:a', rows)
        state = audit.read()
        self.assertEqual(state['retired_counts']['horizon_observed'], 1)
        self.assertEqual(set(state['finished_tokens']['solana:a']), {'retired_at', 'reason'})

    def test_completed_case_frees_slot_without_restarting_old_cohort(self):
        with patch.object(audit, 'LIMIT', 1):
            self.observe([pair(address='a')])
            self.observe([pair(address='a', price=2)], self.now + timedelta(hours=73))
            rows = self.observe([pair(address='a', price=7), pair(address='b')],
                                self.now + timedelta(hours=74))
        self.assertEqual(set(rows), {'solana:b'})
        self.assertEqual(audit.read()['retired_counts']['horizon_observed'], 1)
        self.assertNotIn(('solana', 'a'), audit.watch_targets(self.now + timedelta(hours=74)))

    def test_missing_horizon_quote_retires_without_zero_or_final_price(self):
        self.observe([pair(address='a', price=3)])
        self.assertIn('solana:a', self.observe([], self.now + timedelta(hours=95)))
        self.assertNotIn('solana:a', self.observe([], self.now + timedelta(hours=96)))
        state = audit.read()
        self.assertEqual(state['retired_counts']['horizon_unknown'], 1)
        self.assertEqual(state['finished_tokens']['solana:a']['reason'], 'horizon_unknown')
        self.assertNotIn('final_price', state['finished_tokens']['solana:a'])
        self.observe([], self.now + timedelta(hours=97))
        self.assertEqual(audit.read()['retired_counts']['horizon_unknown'], 1)

    def test_manual_case_is_preserved_after_tracking_horizon(self):
        chain, mint = next(iter(audit.MANUAL))
        market = pair(address=mint)
        market["chainId"] = chain
        self.observe([market])
        rows = self.observe([], self.now + timedelta(hours=100))
        self.assertIn(chain+':'+mint, rows)
        self.assertEqual(audit.read()['finished_tokens'], {})

    def test_corrupt_retirement_summary_does_not_erase_active_cases(self):
        self.observe([pair()])
        state = audit.read()
        state['finished_tokens'] = []
        with open(audit.FILE, 'w') as handle:
            json.dump(state, handle)
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            self.observe([], self.now + timedelta(hours=96))
        self.assertIn('solana:a', audit.read()['tokens'])

    def test_failed_quotes_do_not_starve_other_monitoring_targets(self):
        self.observe([pair(address=str(i)) for i in range(25)])
        first = set(audit.watch_targets(self.now)) - audit.MANUAL
        self.observe([], self.now + timedelta(minutes=1))
        second = set(audit.watch_targets(self.now + timedelta(minutes=1))) - audit.MANUAL
        self.assertEqual(len(first), 10)
        self.assertEqual(len(second), 10)
        self.assertGreater(len(first | second), 10)


    def test_new_contracts_are_watched_even_without_a_previous_quote(self):
        self.assertTrue(audit.RESEARCH_TARGETS <= set(audit.watch_targets(self.now)))
        state = {"tokens": {}}
        with contextlib.redirect_stdout(io.StringIO()):
            audit.research_watches(state, {}, self.now, fetch_context=lambda *a, **kw: self.fail("no pair"))
        self.assertTrue(all(x["status"] == "NO_QUOTE_THIS_CYCLE"
                            for x in state["research_watch_coverage"]["targets"]))
        self.assertEqual(state["research_watch_history"][0]["context"]["status"], "SIN DATOS")

    def test_rejected_low_liquidity_token_still_gets_descriptive_research(self):
        chain, address = sorted(audit.RESEARCH_TARGETS)[0]
        market = pair(address=address, liquidity=1)
        market["chainId"] = chain
        market["txns"] = {"m5": {"buys": 60, "sells": 40}}
        calls = []
        def fetch(token, now):
            calls.append(token)
            return {"status": "RECHAZA", "reason": "two green bars missing",
                    "pattern_research": {"name": "PULLBACK_RECLAIM_WITH_VOLUME"}}
        state = {}
        with contextlib.redirect_stdout(io.StringIO()):
            audit.research_watches(state, {chain + ":" + address: market}, self.now, fetch)
            audit.research_watches(state, {chain + ":" + address: market},
                                   self.now + timedelta(seconds=20), fetch)
        self.assertEqual(len(calls), 1)
        record = state["research_watch_history"][0]
        self.assertEqual(record["count_thresholds"], {"50": "PASS", "60": "PASS", "75": "FAIL"})
        self.assertIsNone(record["buy_volume_usd"])
        self.assertFalse(record["changes_orders"])
        self.assertNotIn("positions", state)


    def test_evm_checksum_addresses_match_without_merging_chains(self):
        chain, address = sorted(audit.RESEARCH_TARGETS)[0]
        self.assertEqual(chain, "bsc")
        market = pair(address=address.upper())
        market["chainId"] = chain
        state = {}
        with contextlib.redirect_stdout(io.StringIO()):
            audit.research_watches(state, {chain + ":" + address.upper(): market},
                self.now, lambda token, now: {"status": "PASA"})
        self.assertEqual(state["research_watch_history"][0]["context"]["status"], "PASA")
        self.assertTrue(audit.is_manual(chain, address.upper()))
        self.assertFalse(audit.is_manual("solana", address.upper()))

    def test_watch_rotation_and_unavailable_candles_keep_no_fabricated_pattern(self):
        state = {}
        visited = []
        for i, (chain, address) in enumerate(sorted(audit.RESEARCH_TARGETS)):
            market = pair(address=address)
            market["chainId"] = chain
            def fetch(token, now):
                visited.append((token["chain"], token["address"]))
                raise ValueError("provider unavailable")
            with contextlib.redirect_stdout(io.StringIO()):
                audit.research_watches(state, {chain + ":" + address: market},
                                      self.now + timedelta(minutes=i), fetch)
        self.assertEqual(set(visited), audit.RESEARCH_TARGETS)
        self.assertTrue(all(r["context"]["status"] == "SIN DATOS"
                            and "pattern_research" not in r["context"]
                            for r in state["research_watch_history"]))


if __name__ == "__main__":
    unittest.main()




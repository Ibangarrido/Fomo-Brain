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

    def test_sampled_peak_timing_and_pair_comparability_are_research_only(self):
        audit.record_decisions("CONTROL", ["DESCARTE solana:a | ratio compras < 60%"])
        self.observe([pair(address="a", price=1)])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            audit.observe({"0": pair(address="a", price=2, pool="other_pool")},
                          {}, self.now + timedelta(minutes=70))
        summary = next(json.loads(line.split("DESCARTES PICOS MUESTREADOS ", 1)[1])
                       for line in output.getvalue().splitlines()
                       if line.startswith("DESCARTES PICOS MUESTREADOS "))
        top = summary["top_10"][0]
        self.assertEqual(top["sampled_peak_minutes_after_rejection"], 70)
        self.assertFalse(top["sampled_peak_within_60m"])
        self.assertFalse(top["sampled_peak_same_pair"])
        self.assertFalse(top["execution_verified"])
        unknown = audit.sampled_peak_context(
            {"received_at": "bad-date", "pair": "a"},
            {"received_at": self.now.isoformat(), "pair": "a"})
        self.assertIsNone(unknown["sampled_peak_minutes_after_rejection"])
        self.assertIsNone(unknown["sampled_peak_within_60m"])

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

    def test_manual_crash_cases_do_not_inflate_automatic_checkpoint_denominator(self):
        # Post-event videos can be studied but must not reduce prospective coverage.
        manual = "DgpKqhvjwtsFUqyuBhaZxtp62nCWwJoKpx77iDUpump"
        audit.record_decisions("CONTROL", [
            "DESCARTE solana:a | ratio compras < 60%",
            "DESCARTE solana:" + manual + " | liquidez insuficiente"])
        self.observe([pair(address="a"), pair(address=manual)])
        self.observe([], self.now + timedelta(minutes=6))
        coverage = audit.read()["last_cycle_coverage"]["checkpoint_coverage"]
        self.assertEqual(coverage["5m"]["due"], 1)
        self.assertEqual(coverage["5m"]["missing"], 1)
        self.assertEqual(coverage["5m"]["manual_after_event_excluded"], 1)
        self.assertEqual(coverage["15m"]["not_due"], 1)
        self.assertEqual(audit.read()["second_look_summary"]["rejected_automatic_tracked"], 1)

    def test_watch_diagnostics_distinguish_upcoming_from_due_checkpoints(self):
        audit.record_decisions("CONTROL", ["DESCARTE solana:a | ratio compras < 60%"])
        self.observe([pair(address="a")])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            audit.watch_targets(self.now + timedelta(minutes=4))
        lines = output.getvalue().splitlines()
        upcoming = next(json.loads(line.split("WATCH UPCOMING CHECKPOINTS ", 1)[1])
                        for line in lines if line.startswith("WATCH UPCOMING CHECKPOINTS "))
        gaps = next(json.loads(line.split("WATCH CHECKPOINT POOL GAPS ", 1)[1])
                    for line in lines if line.startswith("WATCH CHECKPOINT POOL GAPS "))
        self.assertEqual(upcoming["upcoming_due_by_horizon"]["5m"], 1)
        self.assertEqual(upcoming["next_nominal_run_minutes"], 20)
        # A 30m checkpoint 21 minutes away is outside the next scheduled run;
        # at exactly 20 minutes away it must be counted.
        with contextlib.redirect_stdout(io.StringIO()) as output:
            audit.watch_targets(self.now + timedelta(minutes=9))
        before = next(json.loads(line.split("WATCH UPCOMING CHECKPOINTS ", 1)[1])
                      for line in output.getvalue().splitlines()
                      if line.startswith("WATCH UPCOMING CHECKPOINTS "))
        self.assertEqual(before["upcoming_due_by_horizon"]["30m"], 0)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            audit.watch_targets(self.now + timedelta(minutes=10))
        boundary = next(json.loads(line.split("WATCH UPCOMING CHECKPOINTS ", 1)[1])
                        for line in output.getvalue().splitlines()
                        if line.startswith("WATCH UPCOMING CHECKPOINTS "))
        self.assertEqual(boundary["upcoming_due_by_horizon"]["30m"], 1)
        self.assertEqual(gaps["rejected_due"], 0)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            targets = audit.watch_targets(self.now + timedelta(minutes=5, seconds=30))
        gaps = next(json.loads(line.split("WATCH CHECKPOINT POOL GAPS ", 1)[1])
                    for line in output.getvalue().splitlines()
                    if line.startswith("WATCH CHECKPOINT POOL GAPS "))
        self.assertIn(("solana", "a"), targets)
        self.assertEqual(gaps["ordinary_due"], 1)
        self.assertEqual(gaps["ordinary_due_selected"], 1)
        self.assertEqual(gaps["ordinary_due_missed"], 0)

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

    def test_checkpoint_quality_keeps_late_and_missing_out_of_timely_rate(self):
        audit.record_decisions("CONTROL", ["DESCARTE solana:a | ratio compras < 60%"])
        market = pair(price=1)
        market["_brain_received_at"] = self.now.isoformat()
        self.observe([market])
        self.observe([], self.now + timedelta(minutes=6))
        quality = audit.read()["last_cycle_coverage"]["checkpoint_quality"]
        self.assertEqual(quality["5m"]["due"], 1)
        self.assertEqual(quality["5m"]["timely_pct"], 0.0)
        self.assertEqual(quality["5m"]["late_or_missing_pct"], 100.0)
        self.assertIsNone(quality["15m"]["timely_pct"])
        market["_brain_received_at"] = (self.now + timedelta(minutes=8)).isoformat()
        self.observe([market], self.now + timedelta(minutes=8))
        quality = audit.read()["last_cycle_coverage"]["checkpoint_quality"]
        self.assertEqual((quality["5m"]["late"], quality["5m"]["missing"]), (1, 0))
        self.assertEqual(quality["5m"]["timely_pct"], 0.0)
        market["_brain_received_at"] = (self.now + timedelta(minutes=16)).isoformat()
        self.observe([market], self.now + timedelta(minutes=16))
        quality = audit.read()["last_cycle_coverage"]["checkpoint_quality"]
        self.assertEqual(quality["15m"]["timely_pct"], 100.0)
        self.assertEqual(quality["5m"]["late_or_missing_pct"], 100.0)

    def test_recent_six_hour_checkpoint_cohort_excludes_legacy_and_manual(self):
        manual = "DgpKqhvjwtsFUqyuBhaZxtp62nCWwJoKpx77iDUpump"
        audit.record_decisions("CONTROL", [
            "DESCARTE solana:old | ratio compras < 60%",
            "DESCARTE solana:fresh | ratio compras < 60%",
            "DESCARTE solana:late | ratio compras < 60%",
            "DESCARTE solana:" + manual + " | liquidez insuficiente"])
        self.observe([pair(address="old")], self.now - timedelta(hours=7))
        self.observe([pair(address="fresh"), pair(address="late"),
                      pair(address=manual)], self.now)
        self.observe([pair(address="fresh")], self.now + timedelta(minutes=6))
        self.observe([pair(address="late")], self.now + timedelta(minutes=8))
        coverage = audit.read()["last_cycle_coverage"]
        recent = coverage["recent_6h_rejection_cohort"]
        self.assertEqual((recent["5m"]["due"], recent["5m"]["timely"],
                          recent["5m"]["late"], recent["5m"]["missing"]), (2, 1, 1, 0))
        self.assertEqual(recent["5m"]["timely_pct"], 50.0)
        self.assertEqual(coverage["checkpoint_quality"]["5m"]["due"], 3)
        self.assertIsNone(recent["15m"]["timely_pct"])

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


    def test_watch_rotation_advances_by_full_slot_allocation(self):
        # Twenty eligible contracts and ten automatic slots per cycle:
        # the next cycle must cover the other ten, not nine repeats.
        self.observe([pair(address="rotation" + str(i)) for i in range(20)])
        first = set(audit.watch_targets(self.now)) - audit.MANUAL
        self.observe([], self.now + timedelta(minutes=1))
        second = set(audit.watch_targets(self.now + timedelta(minutes=1))) - audit.MANUAL
        self.assertEqual(len(first), 10)
        self.assertEqual(len(second), 10)
        self.assertFalse(first & second)

    def test_due_rejection_checkpoint_preempts_rotation_without_extra_requests(self):
        # The next ten ordinary slots would omit priority0 at cursor=10.
        # Its 5m checkpoint is due now, so research should sample it first.
        audit.record_decisions("EARLY", ["DESCARTE solana:priority0 | ratio compras < 60%"])
        self.observe([pair(address="priority" + str(i)) for i in range(20)])
        self.observe([], self.now + timedelta(minutes=5))
        targets = set(audit.watch_targets(self.now + timedelta(minutes=5))) - audit.MANUAL
        self.assertEqual(len(targets), 10)
        self.assertIn(("solana", "priority0"), targets)
        # No indefinite priority after the two-minute checkpoint window.
        self.observe([], self.now + timedelta(minutes=8))
        self.assertEqual(len(set(audit.watch_targets(self.now + timedelta(minutes=8))) - audit.MANUAL), 10)

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


    def test_timely_sampled_outcomes_exclude_late_horizon(self):
        audit.record_decisions("CONTROL", ["DESCARTE solana:a | ratio compras < 60%"])
        self.observe([pair(price=1)])
        self.observe([pair(price=1.25)], self.now + timedelta(minutes=6))
        counts = audit.read()["last_cycle_coverage"]["checkpoint_coverage"]
        self.assertEqual(counts["5m"]["on_time_within_120s"], 1)
        self.assertEqual(counts["5m"]["on_time_sampled_up_20pct"], 1)
        self.assertEqual(counts["15m"]["not_due"], 1)
        self.observe([pair(price=.7, pool="new")], self.now + timedelta(minutes=16))
        counts = audit.read()["last_cycle_coverage"]["checkpoint_coverage"]
        self.assertEqual(counts["5m"]["on_time_sampled_up_20pct"], 1)
        self.assertEqual(counts["15m"]["on_time_sampled_down_20pct"], 1)
        self.assertEqual(counts["15m"]["on_time_pair_changed"], 1)
        self.assertEqual(counts["30m"]["not_due"], 1)

    def test_late_checkpoint_does_not_count_as_timely_winner(self):
        audit.record_decisions("CONTROL", ["DESCARTE solana:a | liquidity"])
        self.observe([pair(price=1)])
        self.observe([pair(price=1.5)], self.now + timedelta(minutes=12))
        counts = audit.read()["last_cycle_coverage"]["checkpoint_coverage"]["5m"]
        self.assertEqual(counts["late_over_120s"], 1)
        self.assertEqual(counts["on_time_sampled_up_20pct"], 0)


    def test_second_look_counts_market_requalification_without_authorizing_entry(self):
        audit.record_decisions("EARLY", ["DESCARTE solana:a | ratio compras < 60%"])
        first = pair()
        first["pairCreatedAt"] = int((self.now - timedelta(minutes=3)).timestamp() * 1000)
        first["txns"]["m5"] = {"buys": 45, "sells": 55}
        self.observe([first])
        state = audit.read()
        self.assertEqual(state["second_look_summary"]["with_fresh_second_read"], 0)
        second = pair(price=1.1, liquidity=26000)
        second["pairCreatedAt"] = first["pairCreatedAt"]
        second["txns"]["m5"] = {"buys": 70, "sells": 30}
        row = self.observe([second], self.now + timedelta(minutes=5))["solana:a"]
        recovery = row["first_market_requalification"]
        self.assertEqual(recovery["minutes_since_rejection"], 5)
        self.assertAlmostEqual(recovery["buy_ratio_delta"], .25)
        self.assertFalse(recovery["execution_verified"])
        self.assertFalse(recovery["wallet_risk_checked"])
        summary = audit.read()["second_look_summary"]
        self.assertEqual(summary["first_market_requalification_observed"], 1)
        self.assertEqual(summary["first_requalified_within_15m_same_pair"], 1)
        self.assertEqual(summary["full_entry_eligibility_verified"], 0)
        self.assertEqual(summary["executable_fills_verified"], 0)
        third = pair(price=.8, pool="different")
        third["pairCreatedAt"] = first["pairCreatedAt"]
        third["txns"]["m5"] = {"buys": 10, "sells": 90}
        row = self.observe([third], self.now + timedelta(minutes=16))["solana:a"]
        self.assertEqual(row["first_market_requalification"], recovery)
        self.assertEqual(audit.read()["second_look_summary"]["first_market_requalification_observed"], 1)

    def test_second_look_never_requalifies_missing_or_excessive_market_cap(self):
        audit.record_decisions("EARLY", ["DESCARTE solana:a | ratio compras < 60%"])
        first = pair()
        first["pairCreatedAt"] = int((self.now - timedelta(minutes=3)).timestamp() * 1000)
        first["txns"]["m5"] = {"buys": 40, "sells": 60}
        self.observe([first])
        too_large = pair(price=1.1, liquidity=30000)
        too_large["pairCreatedAt"] = first["pairCreatedAt"]
        too_large["marketCap"] = 2500000
        row = self.observe([too_large], self.now + timedelta(minutes=5))["solana:a"]
        self.assertEqual(row["second_look_history"][-1]["checks"]["market_cap_max_2m"], "FAIL")
        self.assertFalse(row["second_look_history"][-1]["market_gates_pass"])
        self.assertNotIn("first_market_requalification", row)
        missing = pair(price=1.2, liquidity=30000)
        missing["pairCreatedAt"] = first["pairCreatedAt"]
        missing["marketCap"] = None
        row = self.observe([missing], self.now + timedelta(minutes=6))["solana:a"]
        self.assertEqual(row["second_look_history"][-1]["checks"]["market_cap_max_2m"], "UNKNOWN")
        self.assertNotIn("first_market_requalification", row)
        valid = pair(price=1.3, liquidity=30000)
        valid["pairCreatedAt"] = first["pairCreatedAt"]
        row = self.observe([valid], self.now + timedelta(minutes=7))["solana:a"]
        self.assertEqual(row["second_look_history"][-1]["checks"]["market_cap_max_2m"], "PASS")
        self.assertIn("first_market_requalification", row)
        self.assertFalse(row["first_market_requalification"]["execution_verified"])

    def test_market_pulse_counts_fresh_automatic_receipts_not_manual_or_replay(self):
        second_kongo = "2Q3jYQWWzkfZotYMyxzAFwfpFT5RhhBvGS3mk8P7PryF"
        self.assertIn(("solana", second_kongo), audit.RESEARCH_TARGETS)
        automatic = pair(liquidity=12000)
        automatic["marketCap"] = 45000
        automatic["priceChange"] = {"m5": -1}
        automatic["txns"] = {"m5": {"buys": 55, "sells": 45}}
        manual = pair(address=second_kongo)
        manual["marketCap"] = 190000
        manual["priceChange"] = {"m5": 100}
        self.observe([automatic, manual])
        pulse = audit.read()["last_cycle_coverage"]["market_pulse"]
        self.assertEqual(pulse["automatic_fresh_receipts"], 1)
        self.assertEqual(pulse["cap_below_50000"], 1)
        self.assertEqual(pulse["cap_180000_or_more"], 0)
        self.assertEqual(pulse["rolling_5m_abs_change_below_2pct"], 1)
        self.assertEqual(pulse["rolling_5m_negative_buy_count_majority"], 1)
        self.assertEqual(pulse["buy_count_ratio_below_60pct"], 1)
        self.assertEqual(pulse["liquidity_below_20000"], 1)
        replay = pair()
        replay["_brain_received_at"] = self.now.isoformat()
        self.observe([replay], self.now + timedelta(minutes=1))
        self.assertEqual(audit.read()["last_cycle_coverage"]["market_pulse"]["automatic_fresh_receipts"], 0)
        missing = pair(price=1.2)
        missing["marketCap"] = None
        missing["priceChange"] = {}
        missing["txns"] = {"m5": {}}
        missing["liquidity"] = {}
        self.observe([missing], self.now + timedelta(minutes=2))
        pulse = audit.read()["last_cycle_coverage"]["market_pulse"]
        self.assertEqual(pulse["automatic_fresh_receipts"], 1)
        self.assertEqual(pulse["cap_unknown"], 1)
        self.assertEqual(pulse["rolling_5m_change_unknown"], 1)
        self.assertEqual(pulse["buy_count_ratio_unknown"], 1)
        self.assertEqual(pulse["liquidity_unknown"], 1)

    def test_market_pulse_buyer_ratio_bands_are_disjoint_and_research_only(self):
        # Four measured transaction-count ratios plus one unknown; these are
        # NOT distinct wallets, verified candles or executable entries.
        markets = []
        for address, buys, sells in (
                ("below50", 49, 51), ("at50", 50, 50),
                ("below60", 59, 41), ("at60", 60, 40)):
            market = pair(address=address, liquidity=25000)
            market["txns"] = {"m5": {"buys": buys, "sells": sells}}
            markets.append(market)
        unknown = pair(address="unknown", liquidity=25000)
        unknown["txns"] = {"m5": {}}
        markets.append(unknown)
        self.observe(markets)
        pulse = audit.read()["last_cycle_coverage"]["market_pulse"]
        self.assertEqual(pulse["automatic_fresh_receipts"], 5)
        self.assertEqual(pulse["buy_count_ratio_below_50pct"], 1)
        self.assertEqual(pulse["buy_count_ratio_50_to_60pct"], 2)
        self.assertEqual(pulse["buy_count_ratio_at_least_60pct"], 1)
        self.assertEqual(pulse["buy_count_ratio_unknown"], 1)
        self.assertEqual(pulse["buy_count_ratio_below_60pct"], 3)
        self.assertEqual(
            pulse["buy_count_ratio_50_to_60pct_liquidity_at_least_20000"], 2)
        self.assertEqual(sum(pulse[key] for key in (
            "buy_count_ratio_below_50pct", "buy_count_ratio_50_to_60pct",
            "buy_count_ratio_at_least_60pct", "buy_count_ratio_unknown")), 5)

    def test_50_to_60_counterfactual_separates_other_market_gates(self):
        # Only market-screen evidence, never candle, wallet or fill eligibility.
        markets = []
        for address, liquidity in (("passes", 25000), ("fails", 10000),
                                   ("unknown", 25000)):
            market = pair(address=address, liquidity=liquidity)
            market["txns"] = {"m5": {"buys": 55, "sells": 45}}
            market["pairCreatedAt"] = int((self.now - timedelta(minutes=30)).timestamp() * 1000)
            if address == "fails":
                market.setdefault("priceChange", {})["m5"] = -5
            if address == "unknown":
                market["pairCreatedAt"] = None
                market.setdefault("priceChange", {})["m5"] = None
            markets.append(market)
        self.observe(markets)
        pulse = audit.read()["last_cycle_coverage"]["market_pulse"]
        self.assertEqual(pulse["buy_count_ratio_50_to_60pct"], 3)
        self.assertEqual(pulse["buy_count_ratio_50_to_60pct_other_market_gates_pass"], 1)
        self.assertEqual(pulse["buy_count_ratio_50_to_60pct_other_market_gates_fail"], 1)
        self.assertEqual(pulse["buy_count_ratio_50_to_60pct_other_market_gates_unknown"], 1)
        self.assertEqual(pulse["buy_count_ratio_50_to_60pct_liquidity_at_least_20000"], 2)
        # Per-gate reasons overlap: one token can fail liquidity AND momentum.
        self.assertEqual(pulse["buy_count_ratio_50_to_60pct_other_market_gate_fail_reasons"],
                         {"liquidity_20000": 1, "momentum5m_2_60": 1})
        self.assertEqual(pulse["buy_count_ratio_50_to_60pct_other_market_gate_unknown_reasons"],
                         {"momentum5m_2_60": 1, "pair_age_2_60": 1})
        self.assertEqual(sum(pulse[key] for key in (
            "buy_count_ratio_50_to_60pct_other_market_gates_pass",
            "buy_count_ratio_50_to_60pct_other_market_gates_fail",
            "buy_count_ratio_50_to_60pct_other_market_gates_unknown")), 3)

    def test_fhostage_crash_is_research_only_even_with_more_buys(self):
        address = "DgpKqhvjwtsFUqyuBhaZxtp62nCWwJoKpx77iDUpump"
        self.assertIn(("solana", address), audit.RESEARCH_TARGETS)
        market = pair(address=address, price=0.00001, liquidity=2100)
        market["priceChange"] = {"m5": -91.77}
        market["txns"] = {"m5": {"buys": 3017, "sells": 2484}}
        snapshot = self.observe([market])["solana:" + address]["last"]
        risk = snapshot["crash_risk_research"]
        self.assertTrue(risk["price_drop_5m_ge_70pct"])
        self.assertTrue(risk["liquidity_below_20000"])
        self.assertTrue(risk["buyers_outnumber_sellers_during_drop"])
        self.assertEqual(risk["liquidity_removed"], "UNKNOWN")
        self.assertEqual(risk["buy_sell_volume_usd"], "UNKNOWN")
        self.assertFalse(risk["sell_execution_verified"])
        self.assertFalse(risk["entry_authorized"])
        self.assertFalse(snapshot["execution_verified"])

    def test_crash_research_does_not_turn_missing_data_into_safe_signal(self):
        address = "DgpKqhvjwtsFUqyuBhaZxtp62nCWwJoKpx77iDUpump"
        market = pair(address=address)
        market["priceChange"] = {}
        market["liquidity"] = {}
        market["txns"] = {"m5": {}}
        snapshot = self.observe([market])["solana:" + address]["last"]
        risk = snapshot["crash_risk_research"]
        self.assertEqual(risk["price_drop_5m_ge_70pct"], "UNKNOWN")
        self.assertEqual(risk["liquidity_below_20000"], "UNKNOWN")
        self.assertEqual(risk["buyers_outnumber_sellers_during_drop"], "UNKNOWN")
        self.assertFalse(risk["entry_authorized"])

    def test_crash_interval_requires_same_pair_and_observed_liquidity(self):
        address = "DgpKqhvjwtsFUqyuBhaZxtp62nCWwJoKpx77iDUpump"
        first = pair(address=address, price=1, liquidity=30000)
        row = self.observe([first])["solana:" + address]
        self.assertIsNone(row["last"]["crash_risk_research"]["interval_minutes"])
        second = pair(address=address, price=.2, liquidity=2000)
        second["txns"] = {"m5": {"buys": 60, "sells": 40}}
        row = self.observe([second], self.now + timedelta(minutes=15))["solana:" + address]
        risk = row["last"]["crash_risk_research"]
        self.assertTrue(risk["previous_receipt_comparable"])
        self.assertEqual(risk["interval_minutes"], 15)
        self.assertAlmostEqual(risk["observed_price_change_between_receipts_pct"], -80)
        self.assertAlmostEqual(risk["observed_liquidity_change_between_receipts_pct"], (2000/30000-1)*100)
        self.assertTrue(risk["buy_count_majority_during_observed_interval_drop"])
        self.assertFalse(risk["entry_authorized"])
        changed = pair(address=address, price=.01, liquidity=1, pool="another_pool")
        row = self.observe([changed], self.now + timedelta(minutes=16))["solana:" + address]
        risk = row["last"]["crash_risk_research"]
        self.assertFalse(risk["previous_receipt_comparable"])
        self.assertIsNone(risk["observed_liquidity_change_between_receipts_pct"])
        self.assertEqual(risk["buy_count_majority_during_observed_interval_drop"], "UNKNOWN")
        missing = pair(address=address, price=.009, pool="another_pool")
        missing["liquidity"] = {}
        row = self.observe([missing], self.now + timedelta(minutes=17))["solana:" + address]
        self.assertIsNone(row["last"]["crash_risk_research"]["observed_liquidity_change_between_receipts_pct"])

    def test_pofd_bsc_is_manual_research_only(self):
        address = "0xc73ff93417777c31a579f5d48cbe0496da267777"
        self.assertIn(("bsc", address), audit.RESEARCH_TARGETS)
        self.assertTrue(audit.is_manual("bsc", address.upper()))
        self.assertFalse(audit.is_manual("solana", address))
        self.assertIn(("bsc", address), audit.watch_targets(self.now))


if __name__ == "__main__":
    unittest.main()




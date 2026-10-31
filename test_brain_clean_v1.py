import unittest
from unittest.mock import patch
import brain_clean_v1 as brain


def sample(cap, ts, key="mint:pool", price=None):
    return {"key": key, "address": "mint", "pool": "pool", "symbol": "TEST",
            "cap": float(cap), "price": float(price if price is not None else cap / 100000),
            "liquidity": 15000, "volume1h": 12000, "buys5m": 16,
            "sells5m": 10, "age_seconds": 3600, "ts": ts}


class CleanPaperTests(unittest.TestCase):
    def test_shadow_provenance_uses_pr_head_not_github_merge_sha(self):
        import os
        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_SHA": "merge-commit",
            "CLEAN_SHADOW_HEAD_SHA": "checked-out-head",
        }, clear=True):
            self.assertEqual(brain.execution_sha(), "checked-out-head")
        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "schedule",
            "GITHUB_SHA": "main-commit",
            "CLEAN_SHADOW_HEAD_SHA": "must-not-override-main",
        }, clear=True):
            self.assertEqual(brain.execution_sha(), "main-commit")
        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_SHA": "merge-commit",
        }, clear=True):
            self.assertEqual(brain.execution_sha(), "merge-commit")

    def test_recent_major_collapse_blocks_dead_cat_staircase(self):
        state = brain.new_state()
        # Real failure shape: an earlier ~400k peak preceded a 40-60k
        # local staircase, then a >95% simulated loss on PILLSEY.
        for cap, ts in [(397721, 500), (60000, 1000), (42000, 1060),
                        (45000, 1120), (50000, 1180)]:
            report = brain.step(state, [sample(cap, ts)], ts)
        self.assertEqual(report["counts"].get("recent_crash_risk"), 1)
        self.assertEqual(state["cash"], 100)
        self.assertEqual(state["positions"], {})
        self.assertEqual(brain.staircase(state["history"]["mint:pool"][-4:])[0], True)

    def test_old_peak_outside_crash_window_does_not_block_staircase(self):
        state = brain.new_state()
        for cap, ts in [(397721, 100), (60000, 3000), (42000, 3060),
                        (45000, 3120), (50000, 3180)]:
            report = brain.step(state, [sample(cap, ts)], ts)
        self.assertEqual(report["counts"].get("paper_entry"), 1)
        self.assertEqual(state["cash"], 90)

    def test_lumi_variants_share_one_slot_across_restored_runs(self):
        import json
        state = brain.new_state()
        for i, cap in enumerate([60000, 42000, 45000, 50000]):
            now = 1000 + i * 60
            rows = []
            for mint, symbol in (("first", "LUMI"), ("second", "Lumi"),
                                 ("third", " $ＬＵＭＩ "), ("other", "OTHER")):
                row = sample(cap, now, key=mint + ":pool")
                row.update(address=mint, symbol=symbol)
                rows.append(row)
            report = brain.step(state, rows, now)
            state = json.loads(json.dumps(state))
        self.assertEqual(set(state["positions"]), {"first:pool", "other:pool"})
        self.assertEqual(state["cash"], 80)
        self.assertEqual(report["counts"]["same_symbol_exposure_open"], 2)
        # The restriction also holds in a later independent poll after restore.
        row = sample(51000, 1240, key="second:pool")
        row.update(address="second", symbol="lumi")
        report = brain.step(state, [row], 1240)
        self.assertEqual(report["counts"].get("same_symbol_exposure_open"), 1)
        self.assertEqual(state["cash"], 80)

    def test_closed_symbol_does_not_blacklist_other_contract(self):
        state = brain.new_state()
        state["closed"] = [{"key": "old:pool", "symbol": "LUMI"}]
        for i, cap in enumerate([60000, 42000, 45000, 50000]):
            now = 1000 + i * 60
            row = sample(cap, now, key="new:pool")
            row.update(address="new", symbol="Lumi")
            report = brain.step(state, [row], now)
        self.assertEqual(report["counts"].get("paper_entry"), 1)
        self.assertEqual(state["closed"], [{"key": "old:pool", "symbol": "LUMI"}])

    def test_tracking_preserves_positions_and_deduplicates_before_limit(self):
        state = brain.new_state()
        state["positions"] = {"held:pool": {}}
        for i in range(12):
            s = sample(60000, 1000 + i, key="old:pool" + str(i))
            s["address"] = "old"
            s["age_seconds"] = 10 * 86400
            state["history"][s["key"]] = [s]
        fresh = sample(60000, 2000, key="fresh:pool")
        fresh["address"] = "fresh"
        state["history"][fresh["key"]] = [fresh]
        priority = brain.tracking_priority(state)
        self.assertEqual(priority[:2], ["held", "fresh"])
        self.assertNotIn("old", priority)
        self.assertEqual(len(priority), len(set(priority)))

    def test_restored_open_position_survives_main_and_records_provenance(self):
        import tempfile, os, json
        state = brain.new_state()
        state["cash"] = 90
        state["positions"]["held:pool"] = {"key": "held:pool", "units": 9.9,
                                                "entry_price": 1, "cost": 10}
        state["last_run"] = {"id": "prior", "completed_at": brain.utcnow()}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            brain.save_json(path, state)
            restored = brain.load_state(path)
            with patch.object(brain, "STATE_FILE", path), \
                 patch.object(brain, "REPORT_FILE", os.path.join(tmp, "report.json")), \
                 patch.object(brain, "POLL_CYCLES", 1), \
                 patch.object(brain, "fetch_pairs", return_value=[]), \
                 patch.object(brain, "load_state", return_value=restored), \
                 patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_run", "GITHUB_SHA": "exact"}):
                brain.main()
            with open(path) as handle:
                saved = json.load(handle)
            with open(os.path.join(tmp, "report.json")) as handle:
                report = json.load(handle)
        self.assertEqual(saved["cash"], 90)
        self.assertIn("held:pool", saved["positions"])
        self.assertEqual(report["previous_run"]["id"], "prior")
        self.assertEqual(saved["last_run"]["event"], "workflow_run")
        self.assertIsNone(report["equity_eur"])

    def test_fetch_budget_stops_search_without_losing_held_quote(self):
        import io, json
        payload = [{"chainId": "solana", "pairAddress": "pool",
                    "baseToken": {"address": "held", "symbol": "HELD"}}]
        clock = iter([0, 0, 1, 46])
        with patch("brain_clean_v1.time.monotonic", side_effect=lambda: next(clock)), \
             patch("brain_clean_v1.discover_recent_addresses", return_value=[]), \
             patch("brain_clean_v1.time.sleep"), \
             patch("brain_clean_v1.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as http:
            pairs = brain.fetch_pairs(queries=("meme",), tracked_addresses=("held",))
        self.assertEqual(len(pairs), 1)
        self.assertEqual(http.call_count, 1)

    def test_recent_profile_source_is_attributed_without_changing_trade_gates(self):
        import io
        import json
        payload = [{"chainId": "solana", "pairAddress": "pool",
                    "baseToken": {"address": "newmint", "symbol": "TEST"},
                    "priceUsd": "1", "marketCap": 60000, "liquidity": {"usd": 100},
                    "pairCreatedAt": 1000000}]
        with patch("brain_clean_v1.discover_recent_addresses", return_value=["newmint"]):
            with patch("brain_clean_v1.urllib.request.urlopen",
                       side_effect=lambda *args, **kwargs: io.BytesIO(json.dumps(payload).encode())):
                with patch("brain_clean_v1.time.sleep"):
                    pairs = brain.fetch_pairs(queries=(), tracked_addresses=())
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["_clean_source"], "recent_profile")
        self.assertEqual(brain.gate(brain.sample(pairs[0], 4000)), "low_liquidity")

    def test_recent_discovery_keeps_only_bounded_solana_addresses(self):
        import io
        import json
        payload = [{"chainId": "ethereum", "tokenAddress": "wrong"},
                   {"chainId": "solana", "tokenAddress": "mintA"},
                   {"chainId": "solana", "tokenAddress": "mintA"},
                   {"chainId": "solana", "tokenAddress": "mintB"}]
        with patch("brain_clean_v1.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(payload).encode())):
            self.assertEqual(brain.discover_recent_addresses(limit=1), ["mintA"])

    def test_audit_quarantines_extreme_quote_and_preserves_cash(self):
        state = brain.new_state()
        brain.step(state, [sample(60000, 1000)], 1000)
        report = brain.step(state, [sample(60000000, 1920)], 1920)
        self.assertEqual(state["outcomes"], [])
        self.assertEqual(report["counts"]["outcome_quote_anomaly"], 1)
        brain.step(state, [sample(90000, 1980)], 1980)
        self.assertEqual(state["outcomes"], [])
        self.assertEqual(state["cash"], 100)

    def test_audit_ignores_illiquid_baseline(self):
        state = brain.new_state()
        thin = sample(60000, 1000)
        thin["liquidity"] = 10
        brain.step(state, [thin], 1000)
        self.assertEqual(state["watchlist"], {})
        brain.step(state, [sample(90000, 1920)], 1920)
        self.assertEqual(state["outcomes"], [])

    def test_audit_records_sampled_peak_and_contract_count(self):
        state = brain.new_state()
        for key in ("mint:pool", "mint:other"):
            for cap, ts in ((60000, 1000), (90000, 1500), (80000, 1920)):
                brain.step(state, [sample(cap, ts, key=key)], ts)
        report = brain.step(state, [], 1921)
        self.assertEqual(report["validated_outcomes_v2"], 2)
        self.assertEqual(report["validated_rally_contracts_v2"], 1)
        self.assertEqual(state["outcomes"][0]["sampled_peak_pct"], 50)
        self.assertEqual(state["outcomes"][0]["baseline_ts"], 1000)

    def test_legacy_audit_is_preserved_but_not_validated(self):
        state = brain.new_state()
        old = {"key": "mint:pool", "label": "rally_25pct", "return_pct": 100897}
        state["outcomes"] = [old.copy()]
        state["watchlist"]["mint:pool"] = {"price": .001, "ts": 1000, "reason": "low_liquidity"}
        report = brain.step(state, [sample(90000, 1920)], 1920)
        self.assertEqual(state["outcomes"], [old])
        self.assertEqual(report["legacy_outcomes_unvalidated"], 1)
        self.assertEqual(report["validated_outcomes_v2"], 0)

    def test_monitor_loop_stops_with_room_to_save_before_timeout(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as folder:
            state_path = os.path.join(folder, "state.json")
            report_path = os.path.join(folder, "report.json")
            with patch.object(brain, "STATE_FILE", state_path), \
                 patch.object(brain, "REPORT_FILE", report_path), \
                 patch.object(brain, "load_state", return_value=brain.new_state()), \
                 patch.object(brain, "fetch_pairs", return_value=[]) as fetch, \
                 patch.object(brain.time, "monotonic", side_effect=[0, 620, 621]), \
                 patch.object(brain.time, "sleep"):
                brain.main()
            self.assertEqual(fetch.call_count, 1)
            self.assertTrue(os.path.exists(report_path))

    def test_watch_rotation_survives_serialization_and_failed_quotes(self):
        import json
        state = brain.new_state()
        state["positions"] = {"held:pool": {}}
        for token in ("a", "b", "c", "d", "e"):
            state["watchlist"][token + ":pool"] = {"ts": 1000, "price": 1}
        selected = set()
        for _ in range(3):
            requested = brain.tracking_priority(state, now=2000)
            self.assertEqual(requested[0], "held")
            self.assertLessEqual(len(requested), 8)
            selected.update(state["tracking_coverage"]["selected_watch_contracts"])
            # No quotes returned: cursor still advances and survives restoration.
            state = json.loads(json.dumps(state))
        self.assertEqual(selected, {"a", "b", "c", "d", "e"})

    def test_watch_reservations_survive_signal_saturation(self):
        state = brain.new_state()
        for i in range(20):
            row = sample(60000, 1000 + i, key=f"signal{i}:pool")
            row["address"] = f"signal{i}"
            state["history"][row["key"]] = [row]
        state["watchlist"] = {"rejected1:pool": {"ts": 1000},
                              "rejected2:pool": {"ts": 1000},
                              "stale:pool": {"ts": -90000},
                              "bad:pool": {"ts": 1000, "anomaly_seen": True}}
        selected = brain.tracking_priority(state, now=2000)
        self.assertIn("rejected1", selected)
        self.assertIn("rejected2", selected)
        self.assertNotIn("stale", selected)
        self.assertNotIn("bad", selected)
        self.assertEqual(len(selected), 8)

    def test_pool_selection_keeps_exact_holding_and_liquid_discovery_pool(self):
        def pair(token, pool, liquidity):
            return {"baseToken": {"address": token}, "pairAddress": pool,
                    "liquidity": {"usd": liquidity}}
        raw = [pair("held", "original", 10), pair("held", "liquid", 50000),
               pair("new", "thin", 10), pair("new", "best", 20000)]
        selected = brain.select_pairs(raw, {"held:original": {}})
        self.assertEqual({p["pairAddress"] for p in selected}, {"original", "liquid", "best"})

    def test_learning_summary_uses_validated_contracts_and_preserves_ledger(self):
        import copy
        state = brain.new_state()
        state["outcomes"] = [
            {"key": "mint:one", "reason": "waiting", "audit_version": 2, "label": "rally_25pct"},
            {"key": "mint:two", "reason": "waiting", "audit_version": 2, "label": "rally_25pct"},
            {"key": "legacy:pool", "reason": "waiting", "label": "rally_25pct"}]
        state["closed"] = [{"pnl_eur": -9}, {"pnl_eur": 2}]
        before = copy.deepcopy(state)
        report = brain.learning_summary(state)
        self.assertEqual(report["by_rejection_reason"]["waiting"]["rally_contracts"], 1)
        self.assertEqual(report["by_rejection_reason"]["waiting"]["observations"], 2)
        self.assertEqual(report["realized_paper_pnl_eur"], -7)
        self.assertFalse(report["automatic_rule_changes"])
        self.assertEqual(state, before)

    def test_new_ledger_has_100_eur_and_no_legacy(self):
        state = brain.new_state()
        self.assertEqual(state["cash"], 100)
        self.assertEqual(state["positions"], {})
        self.assertNotIn("m4", state)

    def test_staircase_requires_independent_recovery(self):
        series = [sample(c, 1000 + i * 60) for i, c in
                  enumerate([60000, 42000, 45000, 50000])]
        self.assertEqual(brain.staircase(series), (True, "staircase_confirmed"))
        self.assertFalse(brain.staircase(series[:3])[0])

    def test_entry_only_after_confirmed_pattern(self):
        state = brain.new_state()
        base = 1000
        for i, cap in enumerate([60000, 42000, 45000, 50000]):
            report = brain.step(state, [sample(cap, base + i * 60)], base + i * 60)
        self.assertEqual(report["counts"].get("paper_entry"), 1)
        self.assertEqual(state["cash"], 90)
        self.assertEqual(len(state["positions"]), 1)

    def test_old_pattern_cannot_trigger_fast_entry(self):
        series = [sample(c, t) for c, t in
                  zip([60000, 42000, 45000, 50000], [1000, 1100, 1200, 2000])]
        self.assertFalse(brain.staircase(series)[0])

    def test_bell_case_study_uses_exact_contract(self):
        self.assertIn("4SiuAiB3xbE1Se9qxPfmGDZY812SxaeLRg4gwgNLpump",
                      brain.CASE_STUDY_ADDRESSES)

    def test_tracked_token_is_refetched_without_search(self):
        import io
        import json
        payload = [{"chainId": "solana", "pairAddress": "pool",
                    "baseToken": {"address": "mint", "symbol": "TEST"}}]
        def fresh_response(request, timeout=8):
            # Each HTTP request gets its own stream; discovery must not
            # consume the mocked response intended for the tracked pool.
            url = request.full_url
            if "/solana/mint" in url:
                return io.BytesIO(json.dumps(payload).encode())
            if "/solana/newmint" in url:
                return io.BytesIO(b"[]")
            raise AssertionError("Unexpected endpoint: " + url)

        with patch("brain_clean_v1.urllib.request.urlopen",
                   side_effect=fresh_response) as mocked:
            with patch("brain_clean_v1.discover_recent_addresses",
                       return_value=["newmint"]):
                with patch("brain_clean_v1.time.sleep"):
                    pairs = brain.fetch_pairs(queries=(), tracked_addresses=("mint",))
        self.assertEqual(len(pairs), 1)
        self.assertTrue(any("/solana/mint" in call.args[0].full_url
                            for call in mocked.call_args_list))
        self.assertTrue(any("/solana/newmint" in call.args[0].full_url
                            for call in mocked.call_args_list))

    def test_unquoted_position_does_not_disappear(self):
        state = brain.new_state()
        state["positions"]["lost:pool"] = {"key": "lost:pool", "units": 2,
                                             "entry_price": 1, "cost": 2}
        report = brain.step(state, [], 2000)
        self.assertEqual(report["counts"]["position_unpriced_hold"], 1)
        self.assertIn("lost:pool", state["positions"])

    def test_stale_quote_cannot_exit_existing_paper_position(self):
        state = brain.new_state()
        state["positions"]["mint:pool"] = {"key": "mint:pool", "units": 10,
                                           "entry_price": 1, "cost": 10}
        state["history"]["mint:pool"] = [sample(60000, 2000, price=1)]
        stale = sample(45000, 1900, price=.7)
        report = brain.step(state, [stale], 2000)
        self.assertEqual(report["counts"].get("position_stale_quote_hold"), 1)
        self.assertNotIn("paper_exit", report["counts"])
        self.assertEqual(state["cash"], 100)
        self.assertIn("mint:pool", state["positions"])
        self.assertEqual(state["closed"], [])

    def test_pillsey_illiquid_stop_does_not_invent_paper_sale(self):
        # Clean #10 recorded a stop at $2,235.84 liquidity, below MIN_LIQ.
        # Preserve the position and cash rather than crediting an unfillable sale.
        key = ("J5jxG3PFaWpj6BLEQExyC6FSqSvaTKNdQ9G3sZwBpump:"
               "13NbvbDB8ThpQdYXv7TifeU9mFKtJ2TDERpHC7m7ghzz")
        state = brain.new_state()
        state["cash"] = 90.0
        state["positions"][key] = {"key": key, "units": 212264.15094339623,
                                    "entry_price": 4.664e-05, "cost": 10.0}
        state["history"][key] = [sample(46339, 1000, key=key, price=4.664e-05)]
        illiquid = sample(2039, 1600, key=key, price=2.052e-06)
        illiquid["liquidity"] = 2235.84
        report = brain.step(state, [illiquid], 1600)
        self.assertEqual(report["counts"].get("position_low_liquidity_hold"), 1)
        self.assertNotIn("paper_exit", report["counts"])
        self.assertEqual(state["cash"], 90.0)
        self.assertIn(key, state["positions"])
        self.assertEqual(state["closed"], [])

        # A later, independently observed liquid quote can still trigger a stop.
        liquid = sample(2039, 1700, key=key, price=2.052e-06)
        liquid["liquidity"] = brain.MIN_LIQ
        report = brain.step(state, [liquid], 1700)
        self.assertEqual(report["counts"].get("paper_exit"), 1)
        self.assertNotIn(key, state["positions"])
        self.assertEqual(len(state["closed"]), 1)
        self.assertAlmostEqual(state["cash"], 90.4312103773585)

    def test_low_liquidity_is_not_traded(self):
        state = brain.new_state()
        for i, cap in enumerate([60000, 42000, 45000, 50000, 56000]):
            s = sample(cap, 1000 + i * 60)
            s["liquidity"] = 100
            report = brain.step(state, [s], 1000 + i * 60)
        self.assertEqual(report["counts"]["low_liquidity"], 1)
        self.assertEqual(state["cash"], 100)

    def test_rejection_outcome_needs_future_quote(self):
        state = brain.new_state()
        first = sample(60000, 1000)
        brain.step(state, [first], 1000)
        self.assertEqual(len(state["outcomes"]), 0)
        second = sample(90000, 1899)
        brain.step(state, [second], 1899)
        self.assertEqual(len(state["outcomes"]), 0)
        third = sample(90000, 1920)
        brain.step(state, [third], 1920)
        self.assertEqual(state["outcomes"][0]["label"], "rally_25pct")
        self.assertEqual(state["outcomes"][0]["reason"], "waiting_for_4_observations")

    def test_stale_quote_cannot_label_rejection_outcome(self):
        state = brain.new_state()
        state["watchlist"]["mint:pool"] = {
            "price": 1, "ts": 1000, "reason": "waiting_for_4_observations"}
        state["history"]["mint:pool"] = [sample(60000, 2000, price=1)]
        report = brain.step(state, [sample(90000, 1900, price=1.5)], 2000)
        self.assertEqual(state["outcomes"], [])
        self.assertIn("mint:pool", state["watchlist"])
        self.assertNotIn("outcome_rally_25pct", report["counts"])

    def test_shallow_dip_cannot_hide_later_collapse(self):
        series = [sample(c, 1000 + i * 30) for i, c in
                  enumerate([60000, 42000, 10000, 45000, 50000])]
        self.assertFalse(brain.staircase(series)[0])

    def test_pillsey_new_peak_collapse_cannot_reuse_older_staircase(self):
        # Exact Solana mint/pool observed in Clean V1 schedule run 41137991511.
        # The old 27% dip was followed by a higher peak and a 61% collapse.
        mint = "J5jxG3PFaWpj6BLEQExyC6FSqSvaTKNdQ9G3sZwBpump"
        pool = "13NbvbDB8ThpQdYXv7TifeU9mFKtJ2TDERpHC7m7ghzz"
        observed = [
            (0, 56425, 0.00005679),
            (36, 41071, 0.00004134),
            (72, 60555, 0.00006095),
            (108, 76991, 0.00007749),
            (144, 114196, 0.00011490),
            (305, 44804, 0.00004509),
            (341, 46339, 0.00004664),
        ]
        series = [sample(cap, 1000 + offset, key=mint + ":" + pool, price=price)
                  for offset, cap, price in observed]
        for observation in series:
            observation["address"] = mint
            observation["pool"] = pool
            observation["symbol"] = "PILLSEY"
        self.assertEqual(brain.staircase(series), (False, "no_qualified_staircase"))
        state = brain.new_state()
        state["history"][series[0]["key"]] = series[:-1]
        report = brain.step(state, [series[-1]], series[-1]["ts"])
        self.assertNotIn("paper_entry", report["counts"])
        self.assertEqual(state["cash"], 100.0)
        self.assertEqual(state["positions"], {})

    def test_cap_recovery_without_price_pattern_is_rejected(self):
        series = [sample(c, 1000 + i * 30, price=p) for i, (c, p) in
                  enumerate(zip([60000, 42000, 45000, 50000], [1, .2, .3, .4]))]
        self.assertFalse(brain.staircase(series)[0])

    def test_mixed_pools_and_close_timestamps_are_rejected(self):
        series = [sample(c, 1000 + i * 30) for i, c in
                  enumerate([60000, 42000, 45000, 50000])]
        series[0]["key"] = "other:pool"
        self.assertFalse(brain.staircase(series)[0])
        series[0]["key"] = "mint:pool"
        series[-1]["ts"] = series[-2]["ts"] + 10
        self.assertFalse(brain.staircase(series)[0])

    def test_unadmitted_quote_cannot_reuse_previous_signal(self):
        state = brain.new_state()
        state["history"]["mint:pool"] = [sample(c, 1000 + i * 30)
            for i, c in enumerate([60000, 42000, 45000, 50000])]
        report = brain.step(state, [sample(51000, 1100)], 1100)
        self.assertEqual(report["counts"].get("non_independent_observation"), 1)
        self.assertEqual(state["positions"], {})

    def test_stale_or_unliquid_quote_cannot_value_paper_equity(self):
        import tempfile
        import os
        import json
        state = brain.new_state()
        state["cash"] = 90
        state["positions"]["mint:pool"] = {"key": "mint:pool", "units": 10,
                                            "entry_price": 1, "cost": 10}
        state["history"]["mint:pool"] = [sample(60000, 2000, price=1)]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(brain, "STATE_FILE", os.path.join(tmp, "state.json")), \
                 patch.object(brain, "REPORT_FILE", os.path.join(tmp, "report.json")), \
                 patch.object(brain, "POLL_CYCLES", 1), \
                 patch.object(brain, "fetch_pairs", return_value=[]), \
                 patch.object(brain, "load_state", return_value=state):
                brain.main()
            with open(os.path.join(tmp, "report.json")) as f:
                report = json.load(f)
        self.assertIsNone(report["equity_eur"])

    def test_missing_restored_ledger_fails_closed_on_repeat_paper_run(self):
        import os
        import tempfile
        env = {"GITHUB_ACTIONS": "true",
               "GITHUB_WORKFLOW": "Brain Clean V1 - isolated PAPER launch",
               "GITHUB_RUN_NUMBER": "2", "GITHUB_RUN_ATTEMPT": "1"}
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "missing-state.json")
            with patch.dict(os.environ, env):
                with self.assertRaisesRegex(RuntimeError, "refusing ledger reset"):
                    brain.load_state(missing)
                with patch.dict(os.environ, {"GITHUB_RUN_NUMBER": "1",
                                             "GITHUB_RUN_ATTEMPT": "2"}):
                    with self.assertRaisesRegex(RuntimeError, "refusing ledger reset"):
                        brain.load_state(missing)
                with patch.dict(os.environ, {"GITHUB_RUN_NUMBER": "1",
                                             "GITHUB_RUN_ATTEMPT": "1"}):
                    self.assertEqual(brain.load_state(missing)["cash"], 100)

    def test_one_token_cannot_be_traded_twice_via_different_pools(self):
        for previously_closed in (False, True):
            with self.subTest(previously_closed=previously_closed):
                state = brain.new_state()
                prior = {"key": "mint:pool1", "units": 10,
                         "entry_price": 1, "cost": 10}
                if previously_closed:
                    state["closed"].append(prior)
                else:
                    state["positions"]["mint:pool1"] = prior
                    state["cash"] = 90
                for i, cap in enumerate([60000, 42000, 45000, 50000]):
                    now = 1000 + i * 60
                    report = brain.step(state, [
                        sample(cap, now, key="mint:pool2")], now)
                expected = ("already_traded_token" if previously_closed
                            else "already_open_token_other_pool")
                self.assertEqual(report["counts"].get(expected), 1)
                self.assertNotIn("paper_entry", report["counts"])
                self.assertNotIn("mint:pool2", state["positions"])
                self.assertEqual(state["cash"], 100 if previously_closed else 90)

    def test_no_legacy_portfolio_import(self):
        import tempfile
        import json
        import os
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            with open(path, "w") as f:
                json.dump({"version": 10, "cash": 500}, f)
            with self.assertRaises(ValueError):
                brain.load_state(path)


class AuthorizedWriteOffTests(unittest.TestCase):
    def test_exact_holdings_closed_without_crediting_cash_and_only_once(self):
        state = brain.new_state()
        state["cash"] = 64.0955
        for key in brain.USER_PAPER_WRITE_OFFS:
            state["positions"][key] = {"key": key, "symbol": "TEST", "cost": 10, "units": 5}
            state["history"][key] = [{"price": .001, "liquidity": 2000, "ts": 100}]
        other = {"key": "other:pool", "symbol": "RAM", "cost": 10}
        state["positions"]["other:pool"] = other.copy()
        brain.apply_user_paper_write_offs(state)
        brain.apply_user_paper_write_offs(state)
        self.assertEqual(state["cash"], 64.0955)
        self.assertEqual(state["positions"], {"other:pool": other})
        self.assertEqual(len(state["closed"]), 2)
        self.assertEqual(sum(x["pnl_eur"] for x in state["closed"]), -20)
        for row in state["closed"]:
            self.assertIsNone(row["exit_price"])
            self.assertFalse(row["execution_verified"])
            self.assertEqual(row["last_observed_liquidity"], 2000)
        self.assertEqual(len(state["history"]), 2)

    def test_write_off_survives_reload_and_does_not_touch_other_closed_records(self):
        import tempfile, os
        state = brain.new_state()
        key = brain.USER_PAPER_WRITE_OFFS[0]
        state["positions"][key] = {"key": key, "cost": 10}
        state["closed"] = [{"key": "prior:pool", "pnl_eur": 2}]
        brain.apply_user_paper_write_offs(state)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            brain.save_json(path, state)
            restored = brain.load_state(path)
            brain.apply_user_paper_write_offs(restored)
        self.assertEqual(restored, state)
        self.assertEqual(restored["closed"][0], {"key": "prior:pool", "pnl_eur": 2})


if __name__ == "__main__":
    unittest.main()

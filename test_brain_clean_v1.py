import unittest
from unittest.mock import patch
import brain_clean_v1 as brain


def sample(cap, ts, key="mint:pool", price=None):
    return {"key": key, "address": "mint", "pool": "pool", "symbol": "TEST",
            "cap": float(cap), "price": float(price if price is not None else cap / 100000),
            "liquidity": 15000, "volume1h": 12000, "buys5m": 16,
            "sells5m": 10, "age_seconds": 3600, "ts": ts}


class CleanPaperTests(unittest.TestCase):
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
        with patch("brain_clean_v1.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(payload).encode())) as mocked:
            with patch("brain_clean_v1.time.sleep"):
                pairs = brain.fetch_pairs(queries=(), tracked_addresses=("mint",))
        self.assertEqual(len(pairs), 1)
        self.assertIn("/solana/mint", mocked.call_args.args[0].full_url)

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


if __name__ == "__main__":
    unittest.main()

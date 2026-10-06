import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import candle_lab as lab
from test_fomo_v8 import b, pair


def payload(rows):
    return {"data": {"attributes": {"ohlcv_list": rows}}}


def rising_rows():
    return [[600, 1, 1.02, .99, 1.01, 100],
            [660, 1.01, 1.03, 1, 1.02, 100],
            [720, 1.02, 1.04, 1.01, 1.03, 100],
            [780, 1.03, 1.06, 1.02, 1.05, 150],
            [840, 1.05, 1.09, 1.04, 1.08, 160]]


class CandleLabTests(unittest.TestCase):
    def setUp(self):
        lab.CYCLE_CACHE.clear()
        lab.REQUEST_TIMES.clear()

    def test_closed_continuity_and_independent_volume(self):
        result = lab.evaluate_rows(payload(list(reversed(rising_rows()))), 905)
        self.assertEqual(result["status"], "PASA")
        self.assertEqual(result["recent_volume_mean_usd"], 155)
        self.assertEqual(result["previous_volume_mean_usd"], 100)

    def test_unclosed_bar_is_excluded(self):
        rows = rising_rows() + [[900, 1, 2, .5, 1.5, 999999]]
        self.assertEqual(lab.evaluate_rows(payload(rows), 905)["bars"], rising_rows())
        self.assertEqual(lab.evaluate_rows(payload(rising_rows()), 899)["status"], "SIN DATOS")

    def test_missing_stale_and_gapped_are_not_signals(self):
        self.assertEqual(lab.evaluate_rows(payload(rising_rows()[:4]), 905)["status"], "SIN DATOS")
        self.assertEqual(lab.evaluate_rows(payload(rising_rows()), 991)["status"], "SIN DATOS")
        rows = rising_rows()
        rows[2][0] = 540
        self.assertEqual(lab.evaluate_rows(payload(rows), 905)["status"], "SIN DATOS")

    def test_falling_close_volume_and_rejection_wick(self):
        rows = rising_rows()
        rows[-1][4] = 1.04
        self.assertEqual(lab.evaluate_rows(payload(rows), 905)["status"], "RECHAZA")
        rows = rising_rows()
        rows[-1][5] = 1
        self.assertEqual(lab.evaluate_rows(payload(rows), 905)["status"], "RECHAZA")
        rows = rising_rows()
        rows[-1][2] = 1.30
        self.assertEqual(lab.evaluate_rows(payload(rows), 905)["status"], "RECHAZA")

    def test_malformed_and_contradictory_rows(self):
        rows = rising_rows()
        rows[-1][4] = float("nan")
        self.assertEqual(lab.evaluate_rows(payload(rows), 905)["status"], "SIN DATOS")
        rows = rising_rows()
        duplicate = list(rows[-1])
        duplicate[5] = 99
        self.assertEqual(lab.evaluate_rows(payload(rows + [duplicate]), 905)["status"], "SIN DATOS")

    def test_exact_contract_pool_and_solana_case(self):
        token = {"chain": "solana", "pair": "Pool", "address": "Token"}
        p = {"data": {"id": "solana_Pool", "attributes": {"address": "Pool"},
                      "relationships": {"base_token": {"data": {"id": "solana_Token"}}}}}
        self.assertEqual(lab.validate_pool(p, token, "solana"), "Pool")
        bad = copy.deepcopy(p)
        bad["data"]["relationships"]["base_token"]["data"]["id"] = "solana_token"
        with self.assertRaises(ValueError):
            lab.validate_pool(bad, token, "solana")
        bad = copy.deepcopy(p)
        bad["data"]["id"] = "bsc_Pool"
        with self.assertRaises(ValueError):
            lab.validate_pool(bad, token, "solana")

    def test_fetch_uses_exact_token_and_caches_one_cycle(self):
        token = {"chain": "solana", "pair": "Pool", "address": "Token"}
        p = {"data": {"id": "solana_Pool", "attributes": {"address": "Pool"},
                      "relationships": {"quote_token": {"data": {"id": "solana_Token"}}}}}
        calls = []
        def fetch(url):
            calls.append(url)
            return payload(rising_rows()) if "/ohlcv/" in url else p
        self.assertEqual(lab.context(token, fetch, 905)["status"], "PASA")
        lab.context(token, fetch, 906)
        self.assertEqual(len(calls), 2)
        self.assertIn("token=Token", calls[1])
        self.assertIn("currency=usd", calls[1])

    def test_api_errors_and_unsupported_chains_fail_closed(self):
        token = {"chain": "solana", "pair": "Pool", "address": "Token"}
        def fail(url):
            raise ValueError("429")
        self.assertEqual(lab.context(token, fail, 905)["status"], "SIN DATOS")
        token["chain"] = "unknown"
        self.assertEqual(lab.context(token, fail, 905)["status"], "SIN DATOS")

    def test_rate_budget_fails_before_network(self):
        lab.REQUEST_TIMES[:] = [100.] * lab.MAX_REQUESTS_PER_MINUTE
        with patch.object(lab.time, "monotonic", return_value=101.), patch.object(lab.urllib.request, "urlopen") as network:
            with self.assertRaises(ValueError):
                lab.request_json("https://api.geckoterminal.com/api/v2/test")
        network.assert_not_called()

    def test_missing_candles_only_block_filtered_arm(self):
        with patch.object(lab, "context", return_value={"status": "SIN DATOS", "reason": "sin velas"}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(lab.guard(False)({"chain": "solana", "address": "a"}))
                self.assertIn("sin velas", lab.guard(True)({"chain": "solana", "address": "a"}))

    def test_four_books_costs_persistence_and_historical_isolation(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp:
            try:
                os.chdir(temp)
                originals = {b.V10_FILE: '{"historical": "early"}',
                             b.V10_IMPULSE_FILE: '{"historical": "impulse"}'}
                for path, content in originals.items():
                    with open(path, "w") as handle:
                        handle.write(content)
                token = b.analizar_par(pair())
                with patch.object(b, "cotizar_posicion", return_value=(1, 20000, pair())), patch.object(b, "motivo_entrada", return_value=None), patch.object(lab, "context", return_value={"status": "PASA", "policy": "candle-r1"}), contextlib.redirect_stdout(io.StringIO()):
                    lab.run([token], b.simular_cartera)
                    lab.run([token], b.simular_cartera)
                for mode in ("early", "impulse"):
                    for arm in ("control", "velas"):
                        path = "fomo_lab_" + mode + "_" + arm + "_r1.json"
                        with open(path) as handle:
                            state = json.load(handle)
                        self.assertEqual(state["cash"], 95)
                        self.assertEqual(len(state["positions"]), 1)
                        self.assertEqual(len(state["observations"]), 2)
                        self.assertAlmostEqual(state["positions"][0]["mark_net"], 5 * .99 * .98 / (1.01 * 1.02))
                        self.assertEqual(state["positions"][0]["entry_candle_context"]["status"], "PASA")
                for path, content in originals.items():
                    with open(path) as handle:
                        self.assertEqual(handle.read(), content)
            finally:
                os.chdir(cwd)

    def test_filtered_rejection_and_loss_guard_keep_exits(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp:
            try:
                os.chdir(temp)
                token = b.analizar_par(pair())
                file = "fomo_lab_early_velas_r1.json"
                with patch.object(b, "cotizar_posicion", return_value=(1, 20000, pair())), patch.object(b, "motivo_entrada", return_value=None), contextlib.redirect_stdout(io.StringIO()):
                    b.simular_cartera([token], file, entry_guard=lambda fresh: "no candle")
                    with open(file) as handle:
                        self.assertEqual(json.load(handle)["positions"], [])
                    b.simular_cartera([token], file, entry_guard=lambda fresh: None)
                with open(file) as handle:
                    state = json.load(handle)
                state["risk_control"] = {"halted_at": "test", "halt_reason": "halt"}
                with open(file, "w") as handle:
                    json.dump(state, handle)
                with patch.object(b, "cotizar_posicion", return_value=(.5, 20000, pair(price=.5))), contextlib.redirect_stdout(io.StringIO()):
                    b.simular_cartera([], file, entry_guard=lambda fresh: None)
                with open(file) as handle:
                    after = json.load(handle)
                self.assertEqual(after["positions"], [])
                self.assertEqual(len(after["closed"]), 1)
                self.assertLess(after["closed"][0]["profit"], 0)
                self.assertEqual(after["reserve"], 0)
                self.assertEqual(after["risk_control"]["halt_reason"], "halt")
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()

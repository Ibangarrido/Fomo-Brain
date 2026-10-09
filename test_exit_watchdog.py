import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
import fomo_brain as brain
from test_roundtrip_shadow import RoundtripTests  # Include diagnostic tests in existing CI entry point.
from exit_watchdog import ExitWatchdog, ThreadCache, wallet_lock, wallet_transaction, MarketRateLimiter
from route_shadow import RouteShadow, quote, raw_quantity, snapshots, USDC, mint_decimals, token_supply, jupiter_quote, get_json, ProviderHTTPError, position_valuations


class RouteShadowTests(unittest.TestCase):
    def test_http_error_preserves_bounded_public_fields_only(self):
        from urllib.error import HTTPError
        body = io.BytesIO(json.dumps({"errorCode": "TOKEN_NOT_TRADABLE",
            "errorMessage": "No route\n" + "x" * 400, "transaction": "SECRET",
            "headers": {"authorization": "SECRET"}, "error": {"nested": "SECRET"}}).encode())
        error = HTTPError("https://example.invalid/?secret=SECRET", 400, "Bad request", {}, body)
        with patch("route_shadow.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ProviderHTTPError) as raised:
                get_json("https://example.invalid")
        exc = raised.exception
        self.assertEqual(exc.http_status, 400)
        self.assertEqual(exc.provider_error["errorCode"], "TOKEN_NOT_TRADABLE")
        self.assertLessEqual(len(exc.provider_error["errorMessage"]), 240)
        self.assertNotIn("\n", exc.provider_error["errorMessage"])
        self.assertNotIn("SECRET", str(exc) + json.dumps(exc.provider_error))
        self.assertTrue(body.closed)

    def test_http_error_non_json_and_oversize_do_not_leak_or_retry(self):
        from urllib.error import HTTPError
        for payload in (b"<html>SECRET</html>", b'{"errorMessage":"' + b"x" * 5000 + b'"}'):
            body = io.BytesIO(payload)
            error = HTTPError("https://example.invalid", 429, "Limit", {}, body)
            with patch("route_shadow.urllib.request.urlopen", side_effect=error) as opener:
                with self.assertRaises(ProviderHTTPError) as raised:
                    get_json("https://example.invalid")
            self.assertEqual(raised.exception.provider_error, {})
            opener.assert_called_once()
            self.assertTrue(body.closed)

    def test_position_valuation_separates_wallets_units_and_unknown_costs(self):
        item = {"chain": "solana", "address": self.mint, "quantity": 1.23456789,
                "wallets": [{"path": "early.json", "opened_at": "entry1", "dex_mark_at": "old"},
                            {"path": "impulse.json", "opened_at": "entry2"}]}
        observation = {"status": "QUOTE_ONLY", "snapshot_at": "snapshot", "received_at": "receipt",
                       "input_amount_raw": "1234567", "expected_out_usdc": .9, "threshold_usdc": .882}
        before = json.dumps(item)
        marks = position_valuations(item, observation)
        self.assertEqual([m["wallet"] for m in marks], ["early.json", "impulse.json"])
        self.assertEqual(marks[0]["quoted_value_usdc"], .9)
        self.assertEqual(marks[0]["paper_mark_at"], "old")
        self.assertEqual(marks[0]["quote_received_at"], "receipt")
        for mark in marks:
            self.assertIsNone(mark["net_liquidation_value_usdc"])
            self.assertIsNone(mark["network_cost_usdc"])
            self.assertIsNone(mark["market_data_age_seconds"])
            self.assertFalse(mark["fx_applied"])
            self.assertFalse(mark["execution_verified"])
        self.assertEqual(json.dumps(item), before)

    def test_unavailable_position_mark_never_reuses_old_output(self):
        item = {"chain": "solana", "address": self.mint, "quantity": 1,
                "wallets": [{"path": "early.json"}]}
        marks = position_valuations(item, {"status": "UNAVAILABLE", "snapshot_at": "snapshot",
                                          "expected_out_usdc": 999, "threshold_usdc": 999})
        self.assertIsNone(marks[0]["quoted_value_usdc"])
        self.assertIsNone(marks[0]["quoted_threshold_usdc"])

    def test_jupiter_http_diagnostics_reach_log_without_wallet_changes(self):
        item = {"chain": "solana", "address": self.mint, "quantity": 1.23456789,
                "wallets": [{"path": "early.json", "paper_mark_net": 123}]}
        before = json.dumps(item)
        def fetch(url):
            if "api.jup.ag" in url:
                raise ProviderHTTPError(400, {"errorCode": "TOKEN_NOT_TRADABLE"})
            return self.fetcher(self.response(), [])(url)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            RouteShadow(read=lambda: [item], fetch=fetch).tick()
        record = json.loads(next(x[len("JUPITER SHADOW "):] for x in output.getvalue().splitlines()
                                 if x.startswith("JUPITER SHADOW {")))
        self.assertEqual(record["http_status"], 400)
        self.assertEqual(record["provider_error"]["errorCode"], "TOKEN_NOT_TRADABLE")
        self.assertIsNone(record["position_valuations"][0]["quoted_value_usdc"])
        self.assertEqual(json.dumps(item), before)

    mint = "HciAVS1urBtboqhLe59HWiMeeN2McEd6y8h4HGkrpump"

    def response(self):
        return {"success": True, "data": {"inputMint": self.mint, "outputMint": USDC,
                "inputAmount": "1234567", "swapType": "BaseIn", "slippageBps": 200,
                "outputAmount": "900000", "otherAmountThreshold": "882000",
                "priceImpactPct": 1.2, "routePlan": [{"poolId": "test"}]}}

    def fetcher(self, response, urls):
        def fetch(url):
            urls.append(url)
            if "/mint/ids?" in url:
                return {"success": True, "data": [{"address": self.mint, "decimals": 6}]}
            return response
        return fetch

    def test_exact_quantity_readonly_and_units(self):
        urls = []
        result = quote({"chain": "solana", "address": self.mint, "quantity": 1.23456789},
                       self.fetcher(self.response(), urls))
        self.assertEqual(result["input_amount_raw"], "1234567")
        self.assertEqual(result["expected_out_usdc"], .9)
        self.assertFalse(result["execution_verified"])
        self.assertIsNone(result["market_data_age_seconds"])
        self.assertTrue(all("/transaction/" not in u and "wallet" not in u for u in urls))

    def test_wrong_route_or_amount_rejected(self):
        for field, value in (("inputMint", USDC), ("inputAmount", "7"),
                             ("outputMint", self.mint), ("routePlan", [])):
            data = self.response()
            data["data"][field] = value
            with self.assertRaises(ValueError):
                quote({"chain": "solana", "address": self.mint, "quantity": 1.23456789},
                      self.fetcher(data, []))

    def test_quantity_bounds_and_unknown_decimals(self):
        for qty, decimals in (("nan", 6), (0, 6), (-1, 6), (1, None), (1, True), (2**64, 0)):
            with self.assertRaises(ValueError):
                raw_quantity(qty, decimals)

    def test_provider_failure_does_not_change_wallet(self):
        item = {"chain": "solana", "address": self.mint, "quantity": 1.23456789,
                "wallets": [{"path": "test-wallet", "paper_mark_net": 3}]}
        before = json.dumps(item, sort_keys=True)
        watcher = RouteShadow(read=lambda: [item], fetch=lambda url: (_ for _ in ()).throw(TimeoutError()),
                              supply_reader=lambda mint: (_ for _ in ()).throw(TimeoutError()))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            watcher.tick()
        self.assertIn("UNAVAILABLE", output.getvalue())
        self.assertEqual(json.dumps(item, sort_keys=True), before)

    def test_missing_route_preserves_rpc_and_quantity_evidence(self):
        def fetch(url):
            return {"data": []} if "/mint/ids?" in url else {"success": False, "msg": "ROUTE_NOT_FOUND"}
        supply = lambda mint: {"jsonrpc": "2.0", "id": 1, "result": {
            "context": {"slot": 123}, "value": {"amount": "1000000", "decimals": 6}}}
        item = {"chain": "solana", "address": self.mint, "quantity": 1.23456789}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            RouteShadow(read=lambda: [item], fetch=fetch, supply_reader=supply).tick()
        record = json.loads(next(line[len("ROUTE SHADOW "):] for line in output.getvalue().splitlines()
                                 if line.startswith("ROUTE SHADOW {")))
        self.assertEqual(record["status"], "UNAVAILABLE")
        self.assertEqual(record["failure_stage"], "route_validation")
        self.assertEqual(record["mint_metadata"]["context_slot"], 123)
        self.assertEqual(record["input_amount_raw"], "1234567")
        self.assertEqual(record["provider_message"], "ROUTE_NOT_FOUND")
        self.assertFalse(record["execution_verified"])
        self.assertNotIn("expected_out_usdc", record)

    def test_route_timeout_preserves_elapsed_and_request_identity(self):
        trace = {}
        def fetch(url):
            if "/mint/ids?" in url:
                return {"success": True, "data": [{"address": self.mint, "decimals": 6}]}
            raise TimeoutError("provider timeout")
        with self.assertRaises(TimeoutError):
            quote({"chain": "solana", "address": self.mint, "quantity": 1}, fetch, diagnostics=trace)
        self.assertEqual(trace["failure_stage"], "route_request")
        self.assertEqual(trace["output_mint"], USDC)
        self.assertGreaterEqual(trace["quote_request_seconds"], 0)
        self.assertNotIn("expected_out_usdc", trace)

    def jupiter_response(self):
        return {"inputMint": self.mint, "outputMint": USDC, "inAmount": "1234567",
                "outAmount": "900000", "otherAmountThreshold": "882000", "swapMode": "ExactIn",
                "router": "metis", "transaction": None, "slippageBps": 200}

    def test_jupiter_get_quote_has_no_wallet_or_execution_parameters(self):
        urls = []
        def fetch(url):
            urls.append(url)
            return self.jupiter_response()
        result = jupiter_quote(self.mint, "1234567", fetch)
        self.assertEqual(result["expected_out_usdc"], .9)
        self.assertFalse(result["execution_verified"])
        self.assertIn("/swap/v2/order?", urls[0])
        for forbidden in ("taker", "wallet", "execute", "build", "api-key"):
            self.assertNotIn(forbidden, urls[0])

    def test_jupiter_rejects_identity_transaction_errors_and_outputs(self):
        for field, value in (("inputMint", USDC), ("outputMint", self.mint), ("inAmount", "7"),
                             ("transaction", "unexpected transaction"), ("taker", "wallet"),
                             ("errorCode", 1), ("error", "No route"), ("outAmount", "NaN"),
                             ("otherAmountThreshold", "900001"), ("router", "unknown")):
            data = self.jupiter_response()
            data[field] = value
            with self.assertRaises(ValueError):
                jupiter_quote(self.mint, "1234567", lambda url: data)

    def test_jupiter_can_quote_when_raydium_has_no_route_without_wallet_changes(self):
        item = {"chain": "solana", "address": self.mint, "quantity": 1.23456789}
        before = json.dumps(item)
        def fetch(url):
            if "api.jup.ag" in url:
                return self.jupiter_response()
            return self.fetcher({"success": False, "msg": "ROUTE_NOT_FOUND"}, [])(url)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            RouteShadow(read=lambda: [item], fetch=fetch).tick()
        records = output.getvalue().splitlines()
        self.assertIn('"status": "UNAVAILABLE"', next(x for x in records if x.startswith("ROUTE SHADOW {")))
        self.assertIn('"status": "QUOTE_ONLY"', next(x for x in records if x.startswith("JUPITER SHADOW {")))
        self.assertEqual(json.dumps(item), before)

    def test_jupiter_disable_skips_provider(self):
        urls = []
        with patch.dict(os.environ, {"BRAIN_JUPITER_SHADOW": "0"}), contextlib.redirect_stdout(io.StringIO()):
            RouteShadow(read=lambda: [{"chain": "solana", "address": self.mint, "quantity": 1.23456789}],
                        fetch=self.fetcher(self.response(), urls)).tick()
        self.assertFalse(any("api.jup.ag" in url for url in urls))

    def test_jupiter_spacing_is_interruptible_and_at_least_three_seconds(self):
        item = {"chain": "solana", "address": self.mint, "quantity": 1.23456789}
        watcher = RouteShadow(read=lambda: [item, item], fetch=self.fetcher(self.response(), []))
        watcher.roundtrip_enabled = False  # This test isolates the existing exit-quote pacing.
        waits = []
        with patch("route_shadow.time.monotonic", return_value=100), \
                patch.object(watcher.stop_event, "wait", side_effect=lambda seconds: waits.append(seconds) or False), \
                contextlib.redirect_stdout(io.StringIO()):
            watcher.tick()
        self.assertEqual(waits, [0, 3])

    def test_missing_metadata_uses_exact_mint_rpc(self):
        requested = []
        def supply(mint):
            requested.append(mint)
            return {"jsonrpc": "2.0", "id": 1, "result": {
                "context": {"slot": 123}, "value": {"amount": "1000000000", "decimals": 6}}}
        fetch_quote = self.fetcher(self.response(), [])
        def fetch(url):
            return {"success": True, "data": [None]} if "/mint/ids?" in url else fetch_quote(url)
        result = quote({"chain": "solana", "address": self.mint, "quantity": 1.23456789}, fetch, supply)
        self.assertEqual(requested, [self.mint])
        self.assertEqual(result["mint_metadata"]["context_slot"], 123)
        self.assertEqual(result["input_amount_raw"], "1234567")

    def test_rpc_error_or_bad_decimals_fail_closed(self):
        for response in ({"jsonrpc": "2.0", "id": 1, "error": {"code": -32602}},
                         {"jsonrpc": "2.0", "id": 1, "result": {"context": {"slot": 123},
                          "value": {"amount": "100", "decimals": None}}}):
            with self.assertRaises(ValueError):
                mint_decimals(self.mint, lambda url: {"data": []}, lambda mint: response)

    def test_rpc_request_is_supply_read_not_transaction(self):
        with patch("route_shadow.urllib.request.urlopen") as opener:
            opener.return_value.__enter__.return_value.read.return_value = b'{"id":1}'
            token_supply(self.mint)
        request = opener.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["method"], "getTokenSupply")
        self.assertEqual(body["params"][0], self.mint)
        self.assertEqual(opener.call_args.kwargs["timeout"], 5)

    def test_snapshot_skips_busy_wallet_and_never_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "wallet.json")
            contents = json.dumps({"cash": 100, "positions": [{"chain": "solana",
                "address": self.mint, "quantity": 1}]})
            with open(path, "w") as handle:
                handle.write(contents)
            with patch("route_shadow.glob.glob", side_effect=[[path], []]):
                self.assertEqual(len(snapshots()), 1)
            seen = []
            with wallet_lock(path), patch("route_shadow.glob.glob", side_effect=[[path], []]):
                thread = threading.Thread(target=lambda: seen.extend(snapshots()))
                thread.start()
                thread.join(1)
                self.assertFalse(thread.is_alive())
            self.assertEqual(seen, [])
            with open(path) as handle:
                self.assertEqual(handle.read(), contents)


class WatchdogTests(unittest.TestCase):
    def test_provider_specific_pacing_is_shared_without_cross_host_delay(self):
        limiter=MarketRateLimiter(.25, {'api.geckoterminal.com':2.1})
        with patch('exit_watchdog.time.monotonic',return_value=100), \
             patch('exit_watchdog.time.sleep') as sleeper:
            limiter.wait('https://api.geckoterminal.com/a')
            limiter.wait('https://api.dexscreener.com/a')
            sleeper.assert_not_called()
            limiter.wait('https://api.geckoterminal.com/b')
            self.assertAlmostEqual(sleeper.call_args.args[0],2.1)

    def test_cache_isolation(self):
        cache = ThreadCache()
        cache["main"] = 1
        seen = []
        def worker():
            seen.append(dict(cache))
            cache["worker"] = 2
            cache.clear()
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertEqual(seen, [{}])
        self.assertEqual(dict(cache), {"main": 1})

    def test_wallet_writes_are_serialized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "wallet.json")
            entered = threading.Event()
            @wallet_transaction
            def write(paper_file):
                entered.set()
            with wallet_lock(path):
                thread = threading.Thread(target=write, args=(path,))
                thread.start()
                self.assertFalse(entered.wait(.02))
            thread.join()
            self.assertTrue(entered.is_set())

    def test_other_wallet_not_blocked_by_busy_wallet(self):
        entered = threading.Event()
        release = threading.Event()
        def owner():
            with wallet_lock(brain.V10_FILE):
                entered.set()
                release.wait(2)
        thread = threading.Thread(target=owner)
        thread.start()
        self.assertTrue(entered.wait(1))
        try:
            with patch("builtins.open", side_effect=FileNotFoundError), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                brain.refresh_open_positions()
            self.assertIn("POSPUESTO", output.getvalue())
        finally:
            release.set()
            thread.join()

    def test_independent_tick_during_blocked_discovery(self):
        tick = threading.Event()
        def refresh(stop_event):
            tick.set()
        watchdog = ExitWatchdog(refresh, interval=.01, duration=1)
        with contextlib.redirect_stdout(io.StringIO()):
            watchdog.start()
            self.assertTrue(tick.wait(1))
            watchdog.stop()
        self.assertFalse(watchdog.thread.is_alive())

    def test_exit_pass_does_not_create_wallets_or_buy(self):
        with patch("builtins.open", side_effect=FileNotFoundError), \
                patch.object(brain, "simular_cartera") as simulator:
            brain.refresh_open_positions()
        simulator.assert_not_called()

    def test_stop_event_skips_all_wallets(self):
        stop = threading.Event()
        stop.set()
        with patch("builtins.open") as read:
            brain.refresh_open_positions(stop_event=stop)
        read.assert_not_called()

    def test_worker_error_is_observable(self):
        def fail(stop_event):
            raise ValueError("failure")
        worker = ExitWatchdog(fail)
        with contextlib.redirect_stdout(io.StringIO()):
            worker.start()
            worker.thread.join(1)
            worker.stop()
        self.assertIsInstance(worker.error, ValueError)

    def test_session_stops_worker_on_discovery_error(self):
        with patch.dict(os.environ, {"BRAIN_EXIT_WATCHDOG": "1"}), \
                patch.object(brain, "refresh_open_positions"), \
                patch.object(brain, "main", side_effect=ValueError("discovery")), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                brain.run_session(1)
        self.assertIsNone(brain.EXIT_WATCHDOG)
        self.assertIsNone(brain.EXIT_SERVICE_AT)

    def test_exit_tail_covers_remaining_window_without_entries(self):
        worker = ExitWatchdog(lambda stop_event: None)
        with patch.object(brain, "EXIT_WATCHDOG", worker), \
                patch.object(brain.time, "monotonic", side_effect=[898, 899, 900]), \
                patch.object(brain.time, "sleep") as sleeper, \
                patch.object(brain, "main") as discovery:
            brain.finish_exit_window(0)
        self.assertEqual([c.args[0] for c in sleeper.call_args_list], [2, 1])
        discovery.assert_not_called()

    def test_exit_tail_does_not_hide_worker_failure(self):
        worker = ExitWatchdog(lambda stop_event: None)
        worker.error = ValueError("failed quote pass")
        with patch.object(brain, "EXIT_WATCHDOG", worker), \
                patch.object(brain.time, "sleep") as sleeper:
            with self.assertRaises(RuntimeError):
                brain.finish_exit_window(0)
        sleeper.assert_not_called()


if __name__ == "__main__":
    unittest.main()



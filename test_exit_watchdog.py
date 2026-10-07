import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
import fomo_brain as brain
from exit_watchdog import ExitWatchdog, ThreadCache, wallet_lock, wallet_transaction
from route_shadow import RouteShadow, quote, raw_quantity, snapshots, USDC


class RouteShadowTests(unittest.TestCase):
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
        watcher = RouteShadow(read=lambda: [item], fetch=lambda url: (_ for _ in ()).throw(TimeoutError()))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            watcher.tick()
        self.assertIn("UNAVAILABLE", output.getvalue())
        self.assertEqual(json.dumps(item, sort_keys=True), before)

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


if __name__ == "__main__":
    unittest.main()

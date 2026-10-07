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

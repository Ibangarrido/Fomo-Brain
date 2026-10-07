"""Read-only market watcher and serialized paper-wallet writes; no signing or orders."""
import functools
import contextlib
import inspect
import os
import threading
import time
import urllib.parse
from collections.abc import MutableMapping


class ThreadCache(MutableMapping):
    """A tick's quotes never leak into discovery or another thread's tick."""
    def __init__(self):
        self.local = threading.local()

    def _data(self):
        if not hasattr(self.local, "data"):
            self.local.data = {}
        return self.local.data

    def __getitem__(self, key):
        return self._data()[key]

    def __setitem__(self, key, value):
        self._data()[key] = value

    def __delitem__(self, key):
        del self._data()[key]

    def __iter__(self):
        return iter(self._data())

    def __len__(self):
        return len(self._data())


_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def wallet_lock(path):
    key = os.path.abspath(os.fspath(path))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def wallet_transaction(function):
    signature = inspect.signature(function)

    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        arguments = signature.bind(*args, **kwargs)
        arguments.apply_defaults()
        with wallet_lock(arguments.arguments["paper_file"]):
            return function(*args, **kwargs)
    return wrapped


def wallet_fork(paths):
    """Protect one-time lab copies and their sources from concurrent exit writes."""
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            with contextlib.ExitStack() as stack:
                for path in sorted(paths):
                    stack.enter_context(wallet_lock(path))
                return function(*args, **kwargs)
        return wrapped
    return decorate


class MarketRateLimiter:
    """Shared pacing, no catch-up bursts. Provider 429s still fail closed upstream."""
    def __init__(self, interval):
        self.interval = interval
        self.lock = threading.Lock()
        self.next_request = {}

    def wait(self, url):
        host = urllib.parse.urlsplit(url).netloc
        with self.lock:
            now = time.monotonic()
            due = max(now, self.next_request.get(host, now))
            self.next_request[host] = due + self.interval
        if due > now:
            time.sleep(due - now)


class ExitWatchdog:
    """Independent exit-only passes; interval is a target, never a fill guarantee."""
    def __init__(self, refresh, interval=3, duration=900):
        if interval <= 0 or duration <= 0:
            raise ValueError("Watchdog interval/duration must be positive")
        self.refresh = refresh
        self.interval = interval
        self.duration = duration
        self.stop_event = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, name="paper-exit-watchdog")

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        # Wait for the current bounded network request/wallet transaction before
        # artifacts are uploaded. Never leave a writer running after session end.
        self.thread.join()

    def _run(self):
        started = time.monotonic()
        previous = None
        while not self.stop_event.is_set() and time.monotonic() - started < self.duration:
            at = time.monotonic()
            try:
                self.refresh(stop_event=self.stop_event)
            except Exception as exc:
                self.error = exc
                print(f"WATCHDOG ERROR {type(exc).__name__}: {exc}", flush=True)
                return
            elapsed = time.monotonic() - at
            gap = None if previous is None else at - previous
            previous = at
            print(f"WATCHDOG TICK | periodo_real_s={gap} | trabajo_s={elapsed:.3f}"
                  " | objetivo_s=3 | NO es ejecucion real", flush=True)
            # Fixed delay after a slow pass avoids catch-up bursts and saturation.
            wait = self.interval if elapsed >= self.interval else self.interval - elapsed
            remaining = self.duration - (time.monotonic() - started)
            self.stop_event.wait(max(0, min(wait, remaining)))

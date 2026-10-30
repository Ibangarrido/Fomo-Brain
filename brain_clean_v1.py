"""Brain Clean V1: isolated, auditable ESCALERA paper experiment.

Never signs transactions, calls a broker, or imports legacy portfolio state.
All market data is public DexScreener data. A single observation is not a
historical candle: the pattern requires independent snapshots across runs.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

STATE_FILE = "brain_clean_v1_state.json"
REPORT_FILE = "brain_clean_v1_report.json"
START_CASH = 100.0
MAX_ENTRY = 10.0
MAX_POSITIONS = 3
SEARCHES = ("pump", "meme", "cat", "doge", "pepe")
MIN_LIQ = 10000.0
MIN_VOL_1H = 5000.0
MIN_CAP, MAX_CAP = 30000.0, 2000000.0
MIN_BUY_RATIO = 0.50
MAX_SNAPSHOTS = 30
MAX_AGE_SECONDS = 6 * 3600
POLL_CYCLES = 5
POLL_SECONDS = 30
FETCH_BUDGET_SECONDS = 45
SIGNAL_MAX_WINDOW_SECONDS = 8 * 60
# Explicit user-provided case studies: track by contract, never infer from ticker.
CASE_STUDY_ADDRESSES = ("4SiuAiB3xbE1Se9qxPfmGDZY812SxaeLRg4gwgNLpump",)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def number(value):
    try:
        x = float(value)
        return x if x >= 0 and x < float("inf") else 0.0
    except (TypeError, ValueError):
        return 0.0


def new_state():
    return {"version": 1, "cash": START_CASH, "positions": {},
            "history": {}, "closed": [], "decisions": [], "watchlist": {},
            "outcomes": [], "seen_at": utcnow()}


def load_state(path=STATE_FILE):
    if not os.path.exists(path):
        # The first isolated workflow run may bootstrap 100 EUR. Later runs
        # must never silently reset the ledger if artifact restore fails.
        if (os.environ.get("GITHUB_ACTIONS") == "true" and
                os.environ.get("GITHUB_WORKFLOW") == "Brain Clean V1 - isolated PAPER launch" and
                (int(os.environ.get("GITHUB_RUN_NUMBER", "1")) > 1 or
                 int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")) > 1)):
            raise RuntimeError("Clean V1 state missing on repeat PAPER run: refusing ledger reset")
        return new_state()
    with open(path, encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("version") != 1:
        raise ValueError("State version mismatch: refusing to import legacy portfolios")
    return state


def save_json(path, obj):
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temp, path)


def discover_recent_addresses(limit=8):
    """Bounded public token-profile discovery; never bypasses trade gates."""
    url = "https://api.dexscreener.com/token-profiles/latest/v1"
    req = urllib.request.Request(url, headers={"User-Agent": "BrainCleanV1/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            profiles = json.load(response)
        if not isinstance(profiles, list):
            return []
        return list(dict.fromkeys(
            p["tokenAddress"] for p in profiles
            if isinstance(p, dict) and p.get("chainId") == "solana"
            and isinstance(p.get("tokenAddress"), str)
            and p["tokenAddress"].isalnum()
        ))[:limit]
    except (OSError, ValueError, KeyError) as exc:
        print("DISCOVERY_SOURCE_ERROR", str(exc)[:160], flush=True)
        return []


def fetch_pairs(queries=SEARCHES, tracked_addresses=()):
    pairs = {}
    deadline = time.monotonic() + FETCH_BUDGET_SECONDS
    def request_json(url, timeout):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Clean V1 per-poll data budget exhausted")
        req = urllib.request.Request(url, headers={"User-Agent": "BrainCleanV1/1.0"})
        with urllib.request.urlopen(req, timeout=min(timeout, remaining)) as response:
            return json.load(response)
    # New discovery and open holdings receive the budget before broad searches.
    tracked_set = set(list(dict.fromkeys(tracked_addresses))[:8])
    recent_addresses = discover_recent_addresses()
    for address in list(dict.fromkeys(list(dict.fromkeys(tracked_addresses))[:8] + recent_addresses))[:16]:
        if time.monotonic() >= deadline:
            break
        if not address or not address.isalnum():
            continue
        url = "https://api.dexscreener.com/token-pairs/v1/solana/" + address
        try:
            tracked = request_json(url, 8)
            if not isinstance(tracked, list):
                continue
            for pair in tracked:
                if not isinstance(pair, dict) or pair.get("chainId") != "solana":
                    continue
                token = (pair.get("baseToken") or {}).get("address")
                pool = pair.get("pairAddress")
                if token == address and pool:
                    pairs[token + ":" + pool] = {**pair, "_clean_source": "tracked" if address in tracked_set else "recent_profile"}
        except (OSError, ValueError, KeyError) as exc:
            print("TRACKED_SOURCE_ERROR", address[:12], str(exc)[:100], flush=True)
        time.sleep(0.35)
    for query in queries:
        if time.monotonic() >= deadline:
            print("FETCH_BUDGET_EXHAUSTED", flush=True)
            break
        url = "https://api.dexscreener.com/latest/dex/search?q=" + urllib.parse.quote(query)
        try:
            payload = request_json(url, 12)
            for pair in payload.get("pairs") or []:
                if pair.get("chainId") != "solana":
                    continue
                addr = (pair.get("baseToken") or {}).get("address")
                if addr and pair.get("pairAddress"):
                    key = addr + ":" + pair["pairAddress"]
                    pairs.setdefault(key, {**pair, "_clean_source": "search"})
        except (OSError, ValueError, KeyError) as exc:
            print("SOURCE_ERROR", query, str(exc)[:160], flush=True)
        time.sleep(0.35)
    return list(pairs.values())


def sample(pair, now):
    addr = (pair.get("baseToken") or {}).get("address")
    pool = pair.get("pairAddress")
    cap = number(pair.get("marketCap") or pair.get("fdv"))
    liquidity = number((pair.get("liquidity") or {}).get("usd"))
    volume = number((pair.get("volume") or {}).get("h1"))
    tx = (pair.get("txns") or {}).get("m5") or {}
    buys, sells = number(tx.get("buys")), number(tx.get("sells"))
    created = number(pair.get("pairCreatedAt"))
    age = (now - created / 1000) if created else None
    return {"key": addr + ":" + pool, "address": addr, "pool": pool,
            "symbol": (pair.get("baseToken") or {}).get("symbol", ""),
            "cap": cap, "liquidity": liquidity, "volume1h": volume,
            "buys5m": buys, "sells5m": sells,
            "price": number(pair.get("priceUsd")), "age_seconds": age,
            "ts": now}


def gate(s):
    if not s["price"] or not s["cap"] or not s["liquidity"]:
        return "missing_verified_market_quote"
    if s["age_seconds"] is None or s["age_seconds"] < 300:
        return "pair_too_new_or_unknown"
    if s["age_seconds"] > 7 * 24 * 3600:
        return "pair_too_old_for_experiment"
    if s["liquidity"] < MIN_LIQ:
        return "low_liquidity"
    if not MIN_CAP <= s["cap"] <= MAX_CAP:
        return "market_cap_outside_range"
    if s["volume1h"] < MIN_VOL_1H:
        return "low_hourly_volume"
    total = s["buys5m"] + s["sells5m"]
    if total < 10 or s["buys5m"] / total < MIN_BUY_RATIO:
        return "weak_or_unknown_buy_pressure"
    return None


def staircase(samples):
    """Four independent observations: peak -> trough -> recovery -> breakout.

    No future data, no interpolated candles and no stale multi-hour signals.
    """
    recent = samples[-MAX_SNAPSHOTS:]
    if len(recent) < 4:
        return False, "waiting_for_4_observations"
    # Only consider a recent sequence: fast memecoin patterns become stale.
    recent = [s for s in recent if recent[-1]["ts"] - s["ts"] <= SIGNAL_MAX_WINDOW_SECONDS]
    if len(recent) < 4:
        return False, "waiting_for_recent_observations"
    if len({int(s["ts"]) for s in recent}) != len(recent):
        return False, "duplicate_observation_times"
    if len({s["key"] for s in recent}) != 1:
        return False, "mixed_pool_observations"
    if any(b["ts"] <= a["ts"] + 20 for a, b in zip(recent, recent[1:])):
        return False, "non_independent_observations"
    if any(not s["price"] or not s["cap"] for s in recent):
        return False, "invalid_pattern_quote"
    a, b = recent[-2:]
    if not (a["cap"] < b["cap"] and a["price"] < b["price"]):
        return False, "no_breakout_confirmation"
    for i in range(1, len(recent) - 2):
        peak_sample = max(recent[:i], key=lambda s: s["cap"])
        peak = peak_sample["cap"]
        trough = recent[i]["cap"]
        if not peak or not trough:
            continue
        # The trough must be the actual low since the selected peak.
        # An older shallow dip must not conceal a later collapse.
        if any(s["cap"] < trough or s["price"] < recent[i]["price"]
               for s in recent[i + 1:]):
            continue
        # A new higher peak before the final confirmation pair starts a new
        # swing. Never reuse an earlier shallow dip after that new peak falls.
        if any(s["cap"] > peak or s["price"] > peak_sample["price"]
               for s in recent[i + 1:-2]):
            continue
        drop = (peak - trough) / peak
        price_drop = 1 - recent[i]["price"] / peak_sample["price"]
        if (0.15 <= drop <= 0.40 and 0.15 <= price_drop <= 0.40 and
                a["cap"] > trough and
                b["cap"] >= trough * 1.10 and
                b["cap"] <= peak * 1.20 and
                a["price"] > recent[i]["price"]):
            return True, "staircase_confirmed"
    return False, "no_qualified_staircase"


def recent_crash_risk(history, latest, lookback_seconds=1800):
    """Block a PAPER re-entry into a collapsed token despite a local staircase.

    A 15-40% local pullback can be a dead-cat bounce after a >60% crash.
    Use only prior independently sampled prices from this same pool, never
    future prices, and keep the existing liquidity/confirmation gates.
    """
    if not latest.get("price") or not latest.get("cap"):
        return False
    earlier = [s for s in history if s["ts"] < latest["ts"]
               and 0 <= latest["ts"] - s["ts"] <= lookback_seconds
               and s.get("key") == latest.get("key")]
    return any(s.get("price", 0) >= latest["price"] * 2.5 or
               s.get("cap", 0) >= latest["cap"] * 2.5 for s in earlier)


def step(state, samples, now=None):
    now = time.time() if now is None else now
    counts = Counter()
    decisions = []
    quotes = {s["key"]: s for s in samples}
    # Existing positions: do not invent an exit when market quotes are missing.
    for key, pos in list(state["positions"].items()):
        s = quotes.get(key)
        if s is None or not s["price"] or not s["liquidity"]:
            counts["position_unpriced_hold"] += 1
            continue
        # A thin pool is not an executable exit quote. Keep the PAPER position,
        # cash and sale history unchanged until liquidity meets the entry guard.
        if s["liquidity"] < MIN_LIQ:
            counts["position_low_liquidity_hold"] += 1
            continue
        # Never simulate an exit from a quote older than the last admitted
        # observation. Out-of-order provider data must not change PAPER cash.
        prior = state["history"].get(key) or []
        if prior and s["ts"] <= prior[-1]["ts"]:
            counts["position_stale_quote_hold"] += 1
            continue
        move = s["price"] / pos["entry_price"] - 1
        if move <= -0.15 or move >= 0.25:
            # Conservative paper estimate: 1% on each side, no guaranteed execution.
            proceeds = pos["units"] * s["price"] * 0.99
            state["cash"] += proceeds
            state["closed"].append({**pos, "exit_at": utcnow(),
                                    "exit_price": s["price"], "proceeds": proceeds,
                                    "pnl_eur": proceeds - pos["cost"],
                                    "exit_reason": "stop_15pct" if move <= -0.15 else "target_25pct"})
            del state["positions"][key]
            counts["paper_exit"] += 1
    state.setdefault("watchlist", {})
    state.setdefault("outcomes", [])
    for s in samples:
        key = s["key"]
        hist = state["history"].setdefault(key, [])
        # Outcomes must use independently admitted, chronological observations.
        admitted = not hist or s["ts"] > hist[-1]["ts"] + 20
        watch = state["watchlist"].get(key)
        if admitted and watch and s["ts"] - watch["ts"] >= 900 and s["price"]:
            change = s["price"] / watch["price"] - 1
            label = "rally_25pct" if change >= .25 else ("drop_30pct" if change <= -.30 else "neutral")
            state["outcomes"].append({"key": key, "reason": watch["reason"],
                                      "return_pct": round(change * 100, 2), "label": label})
            counts["outcome_" + label] += 1
            del state["watchlist"][key]
        # Never use stale or duplicate snapshots as independent observations.
        if admitted:
            hist.append(s)
            hist[:] = [x for x in hist[-MAX_SNAPSHOTS:] if now - x["ts"] <= MAX_AGE_SECONDS]
        reason = gate(s)
        if not reason and not admitted:
            reason = "non_independent_observation"
        if not reason:
            _, reason = staircase(hist)
            if reason == "staircase_confirmed":
                reason = ("recent_crash_risk" if recent_crash_risk(hist, s) else None)
        if not reason and key in state["positions"]:
            reason = "already_open"
        # Pools are not independent assets: one mint may have several pools.
        # Never double PAPER exposure or re-enter a previously traded token
        # by switching its pool address.
        token = s["address"]
        if not reason and any(k.split(":", 1)[0] == token
                              for k in state["positions"]):
            reason = "already_open_token_other_pool"
        if not reason and any(x["key"].split(":", 1)[0] == token
                              for x in state["closed"]):
            reason = "already_traded_token"
        if not reason and len(state["positions"]) >= MAX_POSITIONS:
            reason = "max_3_positions"
        if not reason and state["cash"] < MAX_ENTRY:
            reason = "insufficient_cash"
        if reason:
            counts[reason] += 1
            decisions.append({"key": key, "symbol": s["symbol"], "decision": "REJECT", "reason": reason})
            if s["price"] and key not in state["watchlist"] and reason not in ("already_open", "already_traded"):
                state["watchlist"][key] = {"price": s["price"], "ts": s["ts"], "reason": reason}
            continue
        cost = MAX_ENTRY
        units = cost * 0.99 / s["price"]
        state["cash"] -= cost
        state["positions"][key] = {"key": key, "symbol": s["symbol"],
                                    "entry_at": utcnow(), "entry_price": s["price"],
                                    "units": units, "cost": cost, "entry_cap": s["cap"]}
        counts["paper_entry"] += 1
        decisions.append({"key": key, "symbol": s["symbol"], "decision": "PAPER_ENTRY",
                          "reason": "staircase_confirmed"})
    # Keep memory bounded; never let stale unseen tokens consume storage indefinitely.
    state["history"] = {k: v for k, v in state["history"].items()
                        if v and now - v[-1]["ts"] <= MAX_AGE_SECONDS}
    state["decisions"] = (state["decisions"] + [{"at": utcnow(), **d} for d in decisions])[-1000:]
    state["outcomes"] = state["outcomes"][-1000:]
    state["watchlist"] = dict(sorted(((k, v) for k, v in state["watchlist"].items()
                                      if now - v["ts"] <= 86400),
                                     key=lambda item: item[1]["ts"], reverse=True)[:500])
    return {"at": utcnow(), "candidates": len(samples), "counts": dict(counts),
            "entries": [d for d in decisions if d["decision"] == "PAPER_ENTRY"],
            "cash_eur": round(state["cash"], 4), "open_positions": len(state["positions"]),
            "closed_trades": len(state["closed"]),
            "outcomes_total": len(state["outcomes"]),
            "outcomes_by_label": dict(Counter(x["label"] for x in state["outcomes"])),
            "equity_eur": None, "equity_note": "Unknown until all open positions have current quotes"}


def tracking_priority(state):
    """Holdings first; eligible recent signals before rejected historical pools."""
    recent = sorted((v[-1] for v in state["history"].values() if v and gate(v[-1]) is None),
                    key=lambda s: s["ts"], reverse=True)
    return list(dict.fromkeys(
        [k.split(":", 1)[0] for k in state["positions"]] +
        [s["address"] for s in recent] + list(CASE_STUDY_ADDRESSES)))[:8]


def main():
    state = load_state()
    started = time.monotonic()
    previous_run = state.get("last_run", {})
    now = time.time()
    report = None
    aggregate = Counter()
    discovery_sources = Counter()
    for cycle in range(POLL_CYCLES):
        now = time.time()
        raw = fetch_pairs(tracked_addresses=tracking_priority(state))
        now = time.time()
        samples = [sample(p, now) for p in raw]
        discovery_sources.update(p.get("_clean_source", "unknown") for p in raw)
        observed_contracts = {s["address"] for s in samples}
        for contract in CASE_STUDY_ADDRESSES:
            if contract not in observed_contracts:
                print("CASE_STUDY_NOT_QUOTED", contract, flush=True)
            else:
                print("CASE_STUDY_OBSERVED", contract, flush=True)
        report = step(state, samples, now)
        aggregate.update(report["counts"])
        save_json(STATE_FILE, state)
        print("CLEAN_POLL", cycle + 1, report["counts"], flush=True)
        if cycle < POLL_CYCLES - 1:
            time.sleep(POLL_SECONDS)
    quotes = {s["key"]: s for s in samples}
    if all(k in quotes and quotes[k]["price"] and
           quotes[k]["liquidity"] >= MIN_LIQ and
           (not state["history"].get(k) or
            quotes[k]["ts"] >= state["history"][k][-1]["ts"])
           for k in state["positions"]):
        report["equity_eur"] = round(state["cash"] + sum(
            p["units"] * quotes[k]["price"] * 0.99 for k, p in state["positions"].items()), 4)
        report["equity_note"] = "Mark-to-market estimate with 1% exit cost; no guaranteed fills"
    save_json(STATE_FILE, state)
    report["polls_completed"] = POLL_CYCLES
    report["aggregate_counts"] = dict(aggregate)
    report["discovery_sources_all_polls"] = dict(discovery_sources)
    report["discovery_sources_last_poll"] = dict(Counter(p.get("_clean_source", "unknown") for p in raw))
    report["runtime_seconds"] = round(time.monotonic() - started, 3)
    report["run"] = {"id": os.environ.get("GITHUB_RUN_ID"),
                     "event": os.environ.get("GITHUB_EVENT_NAME"),
                     "sha": os.environ.get("GITHUB_SHA"), "completed_at": utcnow()}
    report["previous_run"] = previous_run
    report["gap_since_previous_run_seconds"] = (
        round(time.time() - datetime.fromisoformat(previous_run["completed_at"]).timestamp(), 1)
        if previous_run.get("completed_at") else None)
    state["last_run"] = report["run"]
    save_json(STATE_FILE, state)
    save_json(REPORT_FILE, report)
    print("BRAIN_CLEAN_V1 " + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()


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
POLL_SECONDS = 50


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
            "history": {}, "closed": [], "decisions": [], "seen_at": utcnow()}


def load_state(path=STATE_FILE):
    if not os.path.exists(path):
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


def fetch_pairs(queries=SEARCHES):
    pairs = {}
    for query in queries:
        url = "https://api.dexscreener.com/latest/dex/search?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={"User-Agent": "BrainCleanV1/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                payload = json.load(response)
            for pair in payload.get("pairs") or []:
                if pair.get("chainId") != "solana":
                    continue
                addr = (pair.get("baseToken") or {}).get("address")
                if addr and pair.get("pairAddress"):
                    key = addr + ":" + pair["pairAddress"]
                    pairs[key] = pair
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
    """At least four separate snapshots: peak, trough, two-step recovery."""
    if len(samples) < 5:
        return False, "waiting_for_5_observations"
    recent = samples[-MAX_SNAPSHOTS:]
    # Avoid claiming a trend from four cached observations with same timestamp.
    if len({int(s["ts"]) for s in recent}) < 4:
        return False, "duplicate_observation_times"
    a, b = recent[-2:]
    if not (a["cap"] < b["cap"] and a["price"] < b["price"]):
        return False, "no_second_recovery_confirmation"
    for i in range(1, len(recent) - 3):
        peak = max(s["cap"] for s in recent[:i])
        trough = recent[i]["cap"]
        if not peak or not trough:
            continue
        drop = (peak - trough) / peak
        if (0.15 <= drop <= 0.40 and
                recent[i + 1]["cap"] > trough and
                a["cap"] > recent[i + 1]["cap"] and
                b["cap"] >= trough * 1.10 and
                b["cap"] <= peak * 1.20):
            return True, "staircase_confirmed"
    return False, "no_qualified_staircase"


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
    for s in samples:
        key = s["key"]
        hist = state["history"].setdefault(key, [])
        # Never use stale or duplicate snapshots as independent observations.
        if not hist or s["ts"] > hist[-1]["ts"] + 20:
            hist.append(s)
            hist[:] = [x for x in hist[-MAX_SNAPSHOTS:] if now - x["ts"] <= MAX_AGE_SECONDS]
        reason = gate(s)
        if not reason:
            _, reason = staircase(hist)
            if reason == "staircase_confirmed":
                reason = None
        if not reason and key in state["positions"]:
            reason = "already_open"
        if not reason and any(x["key"] == key for x in state["closed"]):
            reason = "already_traded"
        if not reason and len(state["positions"]) >= MAX_POSITIONS:
            reason = "max_3_positions"
        if not reason and state["cash"] < MAX_ENTRY:
            reason = "insufficient_cash"
        if reason:
            counts[reason] += 1
            decisions.append({"key": key, "symbol": s["symbol"], "decision": "REJECT", "reason": reason})
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
    return {"at": utcnow(), "candidates": len(samples), "counts": dict(counts),
            "entries": [d for d in decisions if d["decision"] == "PAPER_ENTRY"],
            "cash_eur": round(state["cash"], 4), "open_positions": len(state["positions"]),
            "closed_trades": len(state["closed"]),
            "equity_eur": None, "equity_note": "Unknown until all open positions have current quotes"}


def main():
    state = load_state()
    now = time.time()
    report = None
    for cycle in range(POLL_CYCLES):
        now = time.time()
        raw = fetch_pairs()
        samples = [sample(p, now) for p in raw]
        report = step(state, samples, now)
        save_json(STATE_FILE, state)
        print("CLEAN_POLL", cycle + 1, report["counts"], flush=True)
        if cycle < POLL_CYCLES - 1:
            time.sleep(POLL_SECONDS)
    quotes = {s["key"]: s for s in samples}
    if all(k in quotes and quotes[k]["price"] for k in state["positions"]):
        report["equity_eur"] = round(state["cash"] + sum(
            p["units"] * quotes[k]["price"] * 0.99 for k, p in state["positions"].items()), 4)
        report["equity_note"] = "Mark-to-market estimate with 1% exit cost; no guaranteed fills"
    save_json(STATE_FILE, state)
    save_json(REPORT_FILE, report)
    print("BRAIN_CLEAN_V1 " + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

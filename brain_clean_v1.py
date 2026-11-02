"""Brain Clean V1: isolated, auditable ESCALERA paper experiment.

Never signs transactions, calls a broker, or imports legacy portfolio state.
All market data is public DexScreener data. A single observation is not a
historical candle: the pattern requires independent snapshots across runs.
"""
import json
import math
import os
import time
import unicodedata
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
POLL_CYCLES = 24
RUN_BUDGET_SECONDS = 660
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


USER_EXCLUDED_MINTS = frozenset({
    "nEK7tW9g2ezPciTXMHWf175gXWdMnbjajipTdrXpump",  # MUSKX: user veto
})


def mechanical_staircase_risk(history):
    """Conservative snapshot heuristic, not proof of bots or a future collapse.

    Eight independent same-pool quotes over >=3 minutes, >=20% gain,
    >=85% rising steps and <=3% drawdown in both price and cap.
    Retain the veto for 30 minutes after the observed sequence, so a first
    dip cannot immediately turn the suspicious run into an entry signal.
    This is not a candle/holder analysis: those data are unavailable here.
    """
    if not history:
        return False
    latest_ts = history[-1]["ts"]
    for end in range(8, len(history) + 1):
        window = history[end - 8:end]
        if not 0 <= latest_ts - window[-1]["ts"] <= 1800:
            continue
        if len({s["key"] for s in window}) != 1:
            continue
        if not 180 <= window[-1]["ts"] - window[0]["ts"] <= SIGNAL_MAX_WINDOW_SECONDS:
            continue
        if any(b["ts"] <= a["ts"] + 20 for a, b in zip(window, window[1:])):
            continue
        suspicious = True
        for field in ("price", "cap"):
            values = [s[field] for s in window]
            if any(v <= 0 for v in values):
                suspicious = False
                break
            peak, drawdown = values[0], 0.0
            for value in values:
                peak = max(peak, value)
                drawdown = max(drawdown, 1 - value / peak)
            rising = sum(b > a for a, b in zip(values, values[1:])) / 7
            if values[-1] / values[0] < 1.20 or rising < .85 or drawdown > .03:
                suspicious = False
        if suspicious:
            return True
    return False


def gate(s):
    if s.get("address") in USER_EXCLUDED_MINTS:
        return "user_excluded_muskx"
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


def staircase(samples, min_pullback=0.15):
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
        if any(x["cap"] > peak or x["price"] > peak_sample["price"]
               for x in recent[i + 1:-2]):
            continue
        drop = (peak - trough) / peak
        price_drop = 1 - recent[i]["price"] / peak_sample["price"]
        if (min_pullback <= drop <= 0.40 and min_pullback <= price_drop <= 0.40 and
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


def shadow_three_step_recovery(history):
    """Counterfactual only: require three independent rising price/cap quotes.

    Never gates PAPER entries. Compare its classifications with future
    outcomes before considering any strategy change.
    """
    if len(history) < 3:
        return False
    tail = history[-3:]
    return all(b["ts"] > a["ts"] + 20
               and b["cap"] > a["cap"] and b["price"] > a["price"]
               for a, b in zip(tail, tail[1:]))


def exposure_symbol(symbol):
    """Conservative ticker bucket, not proof that contracts are related."""
    return unicodedata.normalize("NFKC", str(symbol or "")).strip().lstrip("$").strip().casefold()


def step(state, samples, now=None):
    now = time.time() if now is None else now
    counts = Counter()
    decisions = []
    quotes = {s["key"]: s for s in samples}
    # Isolated holdings are not sold or valued, but remain monitored by exact pool.
    for key, pos in state.get("isolated_positions", {}).items():
        audit = pos.setdefault("monitoring_audit", {})
        quote = quotes.get(key)
        if quote is None or not quote.get("price") or not quote.get("liquidity"):
            audit["quote_status"] = "MISSING_OR_INVALID"
            counts["isolated_quote_missing"] += 1
            continue
        ts = quote.get("ts")
        if (not isinstance(ts, (int, float)) or isinstance(ts, bool)
                or not float("-inf") < ts < float("inf")
                or ts > now + 60 or ts < now - MAX_AGE_SECONDS
                or ts < audit.get("last_observed_ts", float("-inf"))):
            audit["quote_status"] = "STALE_FUTURE_OUT_OF_ORDER_OR_UNTIMED"
            counts["isolated_quote_stale"] += 1
            continue
        fingerprint = [quote["price"], quote["liquidity"], quote.get("volume1h")]
        if fingerprint != audit.get("last_snapshot_values"):
            audit["last_snapshot_values"] = fingerprint
            audit["last_snapshot_changed_ts"] = ts
        audit.update({
            "quote_status": "OBSERVED_INDICATIVE_NOT_EXECUTABLE",
            "last_observed_ts": ts, "price_usd": quote["price"],
            "liquidity_usd": quote["liquidity"],
            "volume1h_usd": quote.get("volume1h"),
            "snapshot_unchanged_seconds": round(max(0, ts - audit["last_snapshot_changed_ts"]), 2),
        })
        counts["isolated_quote_observed"] += 1
    # Existing positions: do not invent an exit when market quotes are missing.
    for key, pos in list(state["positions"].items()):
        s = quotes.get(key)
        # A fetch timestamp alone is not proof of a fresh provider quote.
        # Reject malformed, future or aged observations before PAPER exit logic.
        if s is not None:
            observed_ts = s.get("ts")
            if (not isinstance(observed_ts, (int, float))
                    or isinstance(observed_ts, bool)
                    or not float("-inf") < observed_ts < float("inf")
                    or observed_ts > now + 60
                    or observed_ts < now - MAX_AGE_SECONDS):
                pos.setdefault("shadow_exit_audit", {}).update({
                    "quote_status": "INVALID_STALE_OR_FUTURE_TIMESTAMP",
                    "route_status": "UNVERIFIED",
                })
                counts["position_invalid_timestamp_hold"] += 1
                continue
        # SHADOW freshness must never regress on an out-of-order quote.
        # Missing data is a monitoring gap, not evidence of a new price.
        audit = pos.setdefault("shadow_exit_audit", {})
        if s is not None and isinstance(s.get("ts"), (int, float)) and \
                s["ts"] < audit.get("last_observed_ts", float("-inf")):
            counts["shadow_stale_observation_ignored"] += 1
            continue
        if s is None or not s["price"] or not s["liquidity"]:
            audit = pos.setdefault("shadow_exit_audit", {})
            audit["quote_status"] = "MISSING_OR_INVALID"
            audit["route_status"] = "UNVERIFIED"
            counts["position_unpriced_hold"] += 1
            continue
        # SHADOW only: a new retrieval timestamp does not prove the provider
        # published a new market snapshot. Track unchanged quote fields.
        if s["ts"] > audit.get("last_observed_ts", float("-inf")):
            fingerprint = [s["price"], s["liquidity"], s.get("volume1h")]
            if audit.get("last_snapshot_values") == fingerprint:
                audit["consecutive_identical_snapshots"] = (
                    audit.get("consecutive_identical_snapshots", 0) + 1)
                counts["shadow_unchanged_snapshot_observed"] += 1
            else:
                audit["last_snapshot_values"] = fingerprint
                audit["last_snapshot_changed_ts"] = s["ts"]
                audit["consecutive_identical_snapshots"] = 0
            audit["snapshot_unchanged_seconds"] = round(
                max(0, s["ts"] - audit["last_snapshot_changed_ts"]), 2)
        if s["liquidity"] < MIN_LIQ:
            # SHADOW only: observed pool liquidity is not an executable swap route.
            audit = pos.setdefault("shadow_exit_audit", {})
            if audit.get("first_low_liquidity_ts") is None:
                audit["first_low_liquidity_ts"] = s["ts"]
                audit["first_low_liquidity_usd"] = s["liquidity"]
            if s["ts"] >= audit.get("last_observed_ts", float("-inf")):
                audit["last_observed_ts"] = s["ts"]
                audit["last_liquidity_usd"] = s["liquidity"]
                audit["quote_status"] = "OBSERVED_LOW_LIQUIDITY"
            audit["route_status"] = "UNVERIFIED"
            counts["position_low_liquidity_hold"] += 1
            continue
        # A liquid pool is only a recovery of the liquidity indicator, never
        # proof that an external swap route exists or that a fill is possible.
        audit = pos.setdefault("shadow_exit_audit", {})
        if s["ts"] >= audit.get("last_observed_ts", float("-inf")):
            if audit.get("quote_status") == "OBSERVED_LOW_LIQUIDITY":
                audit.setdefault("first_liquidity_recovery_ts", s["ts"])
                counts["shadow_liquidity_recovery_observed"] += 1
            audit["last_observed_ts"] = s["ts"]
            audit["last_liquidity_usd"] = s["liquidity"]
            audit["quote_status"] = "OBSERVED_ABOVE_MIN_LIQ"
            audit["route_status"] = "UNVERIFIED"
        # Never simulate an exit from a quote older than the last admitted
        # observation. Out-of-order provider data must not change PAPER cash.
        prior = state["history"].get(key) or []
        if prior and s["ts"] <= prior[-1]["ts"]:
            counts["position_stale_quote_hold"] += 1
            continue
        move = s["price"] / pos["entry_price"] - 1
        if move <= -0.15 or move >= 0.25:
            # Audit the last admitted quote before the exit, not an invented
            # stop fill. These fields are diagnostic and never change trading.
            previous = prior[-1] if prior else None
            previous_price = previous.get("price") if previous else None
            previous_ts = previous.get("ts") if previous else None
            quote_gap_seconds = (round(s["ts"] - previous_ts, 2)
                                 if isinstance(previous_ts, (int, float)) else None)
            quote_jump_pct = (round((s["price"] / previous_price - 1) * 100, 2)
                              if isinstance(previous_price, (int, float)) and previous_price > 0
                              else None)
            # Conservative paper estimate: 1% on each side, no guaranteed execution.
            proceeds = pos["units"] * s["price"] * 0.99
            state["cash"] += proceeds
            state["closed"].append({**pos, "exit_at": utcnow(),
                                    "exit_price": s["price"], "proceeds": proceeds,
                                    "pnl_eur": proceeds - pos["cost"],
                                    "observed_move_pct": round(move * 100, 2),
                                    "stop_overshoot_pct": round(max(0, -move - .15) * 100, 2),
                                    "stop_breached": move <= -0.15,
                                    "stop_overshoot_alert": move < -0.20,
                                    "stop_overshoot_severity": ("SEVERE" if move < -0.30 else
                                                                "HIGH" if move < -0.20 else
                                                                "NONE"),
                                    "previous_quote_price": previous_price,
                                    "previous_quote_ts": previous_ts,
                                    "exit_quote_ts": s["ts"],
                                    "quote_gap_seconds": quote_gap_seconds,
                                    "quote_jump_pct": quote_jump_pct,
                                    "execution_type": "PAPER_INDICATIVE_UNVERIFIED",
                                    "execution_verified": False,
                                    "realizable_proceeds_eur": None,
                                    "route_status": "UNVERIFIED",
                                    "exit_liquidity_usd": s["liquidity"],
                                    "stop_threshold_pct": -15.0,
                                    "quote_age_at_poll_seconds": round(max(0, now - s["ts"]), 2),
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
        # Research v2 requires liquid baseline and subsequent samples. Old
        # records remain intact but cannot silently become validated evidence.
        if admitted and watch and watch.get("audit_version") == 2:
            if s["price"] and s["liquidity"] >= MIN_LIQ:
                ratio = s["price"] / watch["price"]
                if ratio > 10 or ratio < .1:
                    watch["anomaly_seen"] = True
                    counts["outcome_quote_anomaly"] += 1
                elif not watch.get("anomaly_seen"):
                    watch["peak_price"] = max(watch["peak_price"], s["price"])
                    watch["low_price"] = min(watch["low_price"], s["price"])
                    if s["ts"] - watch["ts"] >= 900:
                        change = ratio - 1
                        label = "rally_25pct" if change >= .25 else ("drop_30pct" if change <= -.30 else "neutral")
                        state["outcomes"].append({
                            "audit_version": 2, "key": key, "address": s["address"],
                            "symbol": s["symbol"], "reason": watch["reason"],
                            "baseline_ts": watch["ts"], "observed_ts": s["ts"],
                            "baseline_price": watch["price"], "observed_price": s["price"],
                            "sampled_peak_pct": round((watch["peak_price"] / watch["price"] - 1) * 100, 2),
                            "sampled_low_pct": round((watch["low_price"] / watch["price"] - 1) * 100, 2),
                            "return_pct": round(change * 100, 2), "label": label})
                        counts["outcome_" + label] += 1
                        del state["watchlist"][key]
        elif admitted and watch:
            # Preserve historical outcomes; restart only the pending research
            # baseline under v2 rules, never wallet balances or trade history.
            del state["watchlist"][key]
        # Never use stale or duplicate snapshots as independent observations.
        if admitted:
            hist.append(s)
            hist[:] = [x for x in hist[-MAX_SNAPSHOTS:] if now - x["ts"] <= MAX_AGE_SECONDS]
        reason = gate(s)
        if not reason and not admitted:
            reason = "non_independent_observation"
        vetoes = state.setdefault("mechanical_veto_until", {})
        vetoes = {k: until for k, until in vetoes.items() if until > now}
        state["mechanical_veto_until"] = vetoes
        if admitted and mechanical_staircase_risk(hist):
            vetoes[s["address"]] = max(vetoes.get(s["address"], 0), s["ts"] + 1800)
        if not reason and vetoes.get(s["address"], 0) > now:
            reason = "mechanical_staircase_risk"
        if not reason:
            _, reason = staircase(hist)
            if reason == "no_qualified_staircase":
                # Prospective 12% vs 15% signal comparison only.
                # Do not change CONTROL entries or book hypothetical proceeds.
                alt_ok, _ = staircase(hist, min_pullback=0.12)
                if alt_ok and not recent_crash_risk(hist, s):
                    counts["shadow_12pct_extra_signal"] += 1
                    decisions.append({"key": key, "symbol": s["symbol"],
                                      "decision": "SHADOW_12PCT_SIGNAL",
                                      "reason": "12pct_pullback_vs_control_15pct",
                                      "quote_ts": s["ts"], "price": s["price"]})
            if reason == "staircase_confirmed":
                reason = ("recent_crash_risk" if recent_crash_risk(hist, s) else None)
                if reason is None:
                    # Shadow-only candidate filter: log a counterfactual,
                    # without changing PAPER entries, stops or risk limits.
                    counts["shadow_three_step_pass" if shadow_three_step_recovery(hist)
                           else "shadow_three_step_would_block"] += 1
        if not reason and key in state.get("isolated_positions", {}):
            reason = "user_isolated_unpriced_token"
        if not reason and key in state["positions"]:
            reason = "already_open"
        # Pools are not independent assets: one mint may have several pools.
        # Never double PAPER exposure or re-enter a previously traded token
        # by switching its pool address.
        token = s["address"]
        if not reason and any(k.split(":", 1)[0] == token
                              for k in state.get("isolated_positions", {})):
            reason = "user_isolated_token_other_pool"
        if not reason and any(k.split(":", 1)[0] == token
                              for k in state["positions"]):
            reason = "already_open_token_other_pool"
        if not reason and any(x["key"].split(":", 1)[0] == token
                              for x in state["closed"]):
            reason = "already_traded_token"
        # Different mints with the same ticker must not occupy all PAPER slots.
        # Apply only to concurrent holdings; a closed ticker is not a blacklist.
        bucket = exposure_symbol(s.get("symbol"))
        if not reason and bucket and any(
                exposure_symbol(p.get("symbol")) == bucket
                for p in state["positions"].values()):
            reason = "same_symbol_exposure_open"
        if not reason and len(state["positions"]) >= MAX_POSITIONS:
            reason = "max_3_positions"
        if not reason and state["cash"] < MAX_ENTRY:
            reason = "insufficient_cash"
        if reason:
            counts[reason] += 1
            decisions.append({"key": key, "symbol": s["symbol"], "decision": "REJECT", "reason": reason})
            if (s["price"] and s["liquidity"] >= MIN_LIQ and s["cap"]
                    and key not in state["watchlist"]
                    and reason not in ("already_open", "already_traded_token", "already_open_token_other_pool")):
                state["watchlist"][key] = {"price": s["price"], "ts": s["ts"], "reason": reason,
                                            "audit_version": 2, "peak_price": s["price"],
                                            "low_price": s["price"]}
            continue
        cost = MAX_ENTRY
        units = cost * 0.99 / s["price"]
        state["cash"] -= cost
        state["positions"][key] = {"key": key, "symbol": s["symbol"],
                                    "entry_at": utcnow(), "entry_price": s["price"],
                                    "units": units, "cost": cost, "entry_cap": s["cap"],
                                    "entry_quote_ts": s["ts"], "entry_liquidity_usd": s["liquidity"]}
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
            "shadow_exit_audit": [
                {"key": k, "entry_liquidity_usd": p.get("entry_liquidity_usd"),
                 "first_low_liquidity_ts": p.get("shadow_exit_audit", {}).get("first_low_liquidity_ts"),
                 "last_liquidity_usd": p.get("shadow_exit_audit", {}).get("last_liquidity_usd"),
                 "quote_status": p.get("shadow_exit_audit", {}).get("quote_status", "UNKNOWN"),
                 "first_liquidity_recovery_ts": p.get("shadow_exit_audit", {}).get("first_liquidity_recovery_ts"),
                 "route_status": "UNVERIFIED",
                 "provider_freshness_verified": False,
                 "snapshot_unchanged_seconds": p.get("shadow_exit_audit", {}).get("snapshot_unchanged_seconds"),
                 "consecutive_identical_snapshots": p.get("shadow_exit_audit", {}).get("consecutive_identical_snapshots", 0),
                 "last_snapshot_changed_ts": p.get("shadow_exit_audit", {}).get("last_snapshot_changed_ts"),
                 "seconds_to_first_low_liquidity":
                    round(p["shadow_exit_audit"]["first_low_liquidity_ts"] - p["entry_quote_ts"], 2)
                    if isinstance(p.get("entry_quote_ts"), (int, float)) and
                    isinstance(p.get("shadow_exit_audit", {}).get("first_low_liquidity_ts"), (int, float))
                    else None}
                for k, p in state["positions"].items()],
            "outcomes_total": len(state["outcomes"]),
            "validated_outcomes_v2": sum(x.get("audit_version") == 2 for x in state["outcomes"]),
            "validated_rally_contracts_v2": len({x["key"].split(":", 1)[0] for x in state["outcomes"]
                if x.get("audit_version") == 2 and x["label"] == "rally_25pct"}),
            "recent_validated_outcomes_v2": [x for x in state["outcomes"] if x.get("audit_version") == 2][-20:],
            "quarantined_watches": sum(bool(w.get("anomaly_seen")) for w in state["watchlist"].values()),
            "legacy_outcomes_unvalidated": sum(x.get("audit_version") != 2 for x in state["outcomes"]),
            "outcomes_by_label": dict(Counter(x["label"] for x in state["outcomes"])),
            "equity_eur": None, "equity_note": "Unknown until all open positions have current quotes"}


def tracking_priority(state, now=None):
    """Holdings first, then signals, with reserved rotating rejected-token slots."""
    now = time.time() if now is None else now
    held = list(dict.fromkeys(k.split(":", 1)[0] for k in
                              list(state["positions"]) + list(state.get("isolated_positions", {}))))
    recent = sorted((v[-1] for v in state["history"].values() if v and gate(v[-1]) is None),
                    key=lambda s: s["ts"], reverse=True)
    watches = sorted({k.split(":", 1)[0] for k, w in state.get("watchlist", {}).items()
                      if 0 <= now - w["ts"] <= 86400 and not w.get("anomaly_seen")
                      and k.split(":", 1)[0] not in held})
    cursor = state.get("watch_cursor", 0)
    rotating = (watches[cursor % len(watches):] + watches[:cursor % len(watches)]) if watches else []
    watch_slots = min(2, len(rotating), max(0, 8 - len(held)))
    chosen_watches = rotating[:watch_slots]
    state["watch_cursor"] = (cursor + watch_slots) % len(watches) if watches else 0
    cases = [a for a in CASE_STUDY_ADDRESSES if a not in held and a not in chosen_watches][:1]
    signal_slots = max(0, 8 - len(held) - watch_slots - len(cases))
    signals = list(dict.fromkeys(x["address"] for x in recent
                                if x["address"] not in held + chosen_watches + cases))[:signal_slots]
    selected = (held + chosen_watches + signals + cases)[:8]
    state["tracking_coverage"] = {"pending_watch_contracts": len(watches),
        "selected_watch_contracts": chosen_watches, "requested_contracts": selected,
        "watch_cursor": state["watch_cursor"]}
    return selected


def select_pairs(raw, positions):
    """One liquid discovery pool per contract; always retain exact holding pools.

    Never splice histories or migrate an existing position to another pool.
    """
    best = {}
    held = {}
    for pair in raw:
        address = (pair.get("baseToken") or {}).get("address")
        pool = pair.get("pairAddress")
        if not address or not pool:
            continue
        key = address + ":" + pool
        if key in positions:
            held[key] = pair
        prior = best.get(address)
        liquidity = number((pair.get("liquidity") or {}).get("usd"))
        if prior is None or liquidity > number((prior.get("liquidity") or {}).get("usd")):
            best[address] = pair
    selected = {((p.get("baseToken") or {})["address"] + ":" + p["pairAddress"]): p
                for p in best.values()}
    selected.update(held)
    return list(selected.values())


def median_quote_gap(stops):
    """Median of nonnegative finite gaps; missing or corrupt legacy data stays unknown."""
    from math import isfinite
    gaps = sorted(float(x["quote_gap_seconds"]) for x in stops
                  if isinstance(x.get("quote_gap_seconds"), (int, float))
                  and not isinstance(x.get("quote_gap_seconds"), bool)
                  and isfinite(x["quote_gap_seconds"]) and x["quote_gap_seconds"] >= 0)
    if not gaps:
        return None
    mid = len(gaps) // 2
    return gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2


def stop_loss_diagnosis(row):
    """Evidence flags, not causal attribution or proof of executable proceeds."""
    if row.get("exit_reason") != "stop_15pct":
        return None
    gap = row.get("quote_gap_seconds")
    jump = row.get("quote_jump_pct")
    liquidity = row.get("exit_liquidity_usd")
    age = row.get("quote_age_at_poll_seconds")
    flags = []
    if isinstance(gap, (int, float)) and not isinstance(gap, bool) and math.isfinite(gap) and gap > 60:
        flags.append("QUOTE_INTERVAL_OVER_60S")
    if isinstance(jump, (int, float)) and not isinstance(jump, bool) and math.isfinite(jump) and jump <= -15:
        flags.append("OBSERVED_PRICE_GAP_15PCT")
    if isinstance(liquidity, (int, float)) and not isinstance(liquidity, bool) and math.isfinite(liquidity) and liquidity < MIN_LIQ:
        flags.append("BELOW_MIN_LIQUIDITY")
    if isinstance(age, (int, float)) and not isinstance(age, bool) and math.isfinite(age) and age > MAX_AGE_SECONDS:
        flags.append("STALE_EXIT_QUOTE")
    if row.get("execution_verified") is not True:
        flags.append("EXECUTION_UNVERIFIED")
    if not isinstance(gap, (int, float)) or isinstance(gap, bool) or not math.isfinite(gap) or gap < 0:
        flags.append("QUOTE_INTERVAL_UNKNOWN")
    if not isinstance(jump, (int, float)) or isinstance(jump, bool) or not math.isfinite(jump):
        flags.append("PRICE_GAP_UNKNOWN")
    return flags


def learning_summary(state):
    """Descriptive evidence from retained validated rows, never an auto-tuner."""
    groups = {}
    for row in state.get("outcomes", []):
        if row.get("audit_version") != 2:
            continue
        group = groups.setdefault(row["reason"], {"observations": 0, "contracts": set(),
                                                  "rally_contracts": set(), "drop_contracts": set()})
        token = row["key"].split(":", 1)[0]
        group["observations"] += 1
        group["contracts"].add(token)
        if row["label"] == "rally_25pct":
            group["rally_contracts"].add(token)
        if row["label"] == "drop_30pct":
            group["drop_contracts"].add(token)
    closed = state.get("closed", [])
    # Diagnostics only: historical stops may lack prior-quote metadata.
    # Never treat a missing audit field as a zero-gap or a verified fill.
    stops = [x for x in closed if x.get("exit_reason") == "stop_15pct"]
    excessive = [x for x in stops if isinstance(x.get("observed_move_pct"), (int, float))
                 and x["observed_move_pct"] < -20]
    audited = [x for x in excessive
               if isinstance(x.get("previous_quote_price"), (int, float))
               and x["previous_quote_price"] > 0
               and isinstance(x.get("quote_gap_seconds"), (int, float))
               and isinstance(x.get("quote_jump_pct"), (int, float))]
    return {"scope": "retained_v2_observations_only; repeated contracts are not independent trials",
            "automatic_rule_changes": False,
            "by_rejection_reason": {reason: {k: len(v) if isinstance(v, set) else v
                                             for k, v in g.items()} for reason, g in groups.items()},
            "closed_paper_trades": len(closed),
            "realized_paper_pnl_eur": round(sum(x.get("pnl_eur", 0) for x in closed), 4),
            "worst_paper_trade_eur": min((x.get("pnl_eur", 0) for x in closed), default=None),
            "stop_overshoot_audit": {
                "stop_exits": len(stops),
                "excessive_stops_below_minus_20pct": len(excessive),
                "excessive_stops_with_prior_quote_audit": len(audited),
                "excessive_stops_missing_prior_quote_audit": len(excessive) - len(audited),
                "excessive_stops_realized_pnl_eur": round(sum(x.get("pnl_eur", 0) for x in excessive), 4),
                "verified_stop_fills": None,
                "classified_high": sum(x.get("stop_overshoot_severity") == "HIGH" for x in stops),
                "classified_severe": sum(x.get("stop_overshoot_severity") == "SEVERE" for x in stops),
                "classification_missing_legacy": sum(
                    x.get("stop_overshoot_severity") not in ("NONE", "HIGH", "SEVERE")
                    for x in stops),
                "median_quote_gap_seconds": median_quote_gap(stops),
                "stop_diagnostic_counts": dict(Counter(
                    flag for x in stops for flag in stop_loss_diagnosis(x))),
                "unverified_stop_exits": sum(
                    x.get("execution_verified") is not True for x in stops),
                "note": "Observed PAPER prices, not guaranteed executable stop fills; legacy rows may lack quote history",
            }}


# Explicit user-authorized PAPER write-offs, keyed by exact mint and pool.
# No simulated sale or recoverable cash is asserted for these illiquid holdings.
USER_PAPER_WRITE_OFFS = (
    "4MinLrUYVTGQ854Jk8WjaxaDMtKHTYRiDqr2BKyCpump:4ksSdLyCtp8XNpoBzS1xoSLpgHCri5D68BLApqsFey1P",
    "HPPspGtHi9kP9RoC2x4qDYbSmrxv7gY1ZRpeEQXqpump:2eo8AZdKQVwccpqUJ4tA7hqBomLoKgS26EUJXxposd4K",
)


def apply_user_paper_write_offs(state):
    """Close only the two authorized PAPER holdings, once, with zero recovery."""
    for key in USER_PAPER_WRITE_OFFS:
        pos = state["positions"].pop(key, None)
        if pos is None:
            continue
        history = state.get("history", {}).get(key) or []
        quote = history[-1] if history else {}
        state["closed"].append({
            **pos, "exit_at": utcnow(), "exit_price": None, "proceeds": 0.0,
            "pnl_eur": -pos["cost"], "exit_reason": "user_authorized_paper_write_off",
            "execution_verified": False, "recovery_assumption": "zero",
            "last_observed_price": quote.get("price"),
            "last_observed_liquidity": quote.get("liquidity"),
            "last_observed_ts": quote.get("ts"),
        })
        print("USER_PAPER_WRITE_OFF", key, "zero recovery; no executed sale", flush=True)


PAPER_ISOLATE_SYMBOLS = frozenset(("MARVIN", "REGRET", "PAWS"))


def isolate_authorized_paper_positions(state):
    """Separate unique authorized PAPER holdings without sale, cash or P&L."""
    positions = state.setdefault("positions", {})
    isolated = state.setdefault("isolated_positions", {})
    for symbol in PAPER_ISOLATE_SYMBOLS:
        matches = [(key, pos) for key, pos in positions.items()
                   if str(pos.get("symbol", "")).strip().upper() == symbol]
        if len(matches) != 1:
            continue  # ambiguous ticker: do not guess contract
        key, pos = matches[0]
        if key in isolated:
            continue
        isolated[key] = {**pos, "isolation_reason": "user_authorized_unverifiable_exit",
                         "isolation_status": "UNPRICED_NOT_SOLD",
                         "realizable_value_eur": None, "route_status": "UNVERIFIED",
                         "isolated_at": utcnow()}
        del positions[key]
    return len(isolated)


def mask_unrealizable_total_equity(report, state):
    """Never label the active-book estimate as total equity with isolated assets."""
    if not state.get("isolated_positions"):
        return
    if report.get("equity_eur") is not None:
        report["active_book_indicative_eur"] = report["equity_eur"]
    report["equity_eur"] = None
    report["equity_note"] = (
        "TOTAL_UNKNOWN: isolated assets have no verified executable exit; "
        "active-book indicative value is not total portfolio equity"
    )


def execution_sha():
    """Report the checked-out PR head in isolated shadow runs, not the PR merge SHA."""
    if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
        return os.environ.get("CLEAN_SHADOW_HEAD_SHA") or os.environ.get("GITHUB_SHA")
    return os.environ.get("GITHUB_SHA")


def main():
    state = load_state()
    apply_user_paper_write_offs(state)
    isolate_authorized_paper_positions(state)
    save_json(STATE_FILE, state)
    started = time.monotonic()
    previous_run = state.get("last_run", {})
    now = time.time()
    first_poll_started_at = now
    report = None
    aggregate = Counter()
    discovery_sources = Counter()
    polls_completed = 0
    selection_counts = Counter()
    for cycle in range(POLL_CYCLES):
        if cycle and time.monotonic() - started >= RUN_BUDGET_SECONDS - FETCH_BUDGET_SECONDS:
            break
        now = time.time()
        raw = fetch_pairs(tracked_addresses=tracking_priority(state))
        selection_counts["raw_pool_observations"] += len(raw)
        raw = select_pairs(raw, {**state.get("isolated_positions", {}),
                                 **state["positions"]})
        selection_counts["selected_pool_observations"] += len(raw)
        now = time.time()
        samples = [sample(p, now) for p in raw]
        coverage = state.get("tracking_coverage", {})
        requested_watches = set(coverage.get("selected_watch_contracts", []))
        received_keys = {x["key"] for x in samples}
        pending_keys = [k for k in state.get("watchlist", {})
                        if k.split(":", 1)[0] in requested_watches]
        coverage["watch_pool_quotes_received"] = sum(k in received_keys for k in pending_keys)
        coverage["watch_pool_quotes_missing"] = sum(k not in received_keys for k in pending_keys)
        discovery_sources.update(p.get("_clean_source", "unknown") for p in raw)
        observed_contracts = {s["address"] for s in samples}
        for contract in CASE_STUDY_ADDRESSES:
            if contract not in observed_contracts:
                print("CASE_STUDY_NOT_QUOTED", contract, flush=True)
            else:
                print("CASE_STUDY_OBSERVED", contract, flush=True)
        report = step(state, samples, now)
        polls_completed += 1
        aggregate.update(report["counts"])
        save_json(STATE_FILE, state)
        print("CLEAN_POLL", cycle + 1, report["counts"], flush=True)
        if cycle < POLL_CYCLES - 1:
            time.sleep(POLL_SECONDS)
    quotes = {s["key"]: s for s in samples}
    if all(k in quotes and quotes[k]["price"] and quotes[k]["liquidity"] >= MIN_LIQ and
           (not state["history"].get(k) or
            quotes[k]["ts"] >= state["history"][k][-1]["ts"])
           for k in state["positions"]):
        report["equity_eur"] = round(state["cash"] + sum(
            p["units"] * quotes[k]["price"] * 0.99 for k, p in state["positions"].items()), 4)
        report["equity_note"] = "Mark-to-market estimate with 1% exit cost; no guaranteed fills"
    mask_unrealizable_total_equity(report, state)
    save_json(STATE_FILE, state)
    report["isolated_positions"] = [{"key": k, "symbol": p.get("symbol"),
        "status": p.get("isolation_status"), "route_status": "UNVERIFIED",
        "realizable_value_eur": None, "monitoring": p.get("monitoring_audit", {})}
        for k, p in state.get("isolated_positions", {}).items()]
    report["polls_completed"] = polls_completed
    report["monitoring_note"] = "Bounded monitoring; GitHub scheduling gaps and stop overshoot remain possible"
    report["aggregate_counts"] = dict(aggregate)
    report["selection_counts"] = dict(selection_counts)
    report["tracking_coverage"] = state.get("tracking_coverage", {})
    report["learning_summary"] = learning_summary(state)
    report["unique_contracts_last_poll"] = len({s["address"] for s in samples})
    report["discovery_sources_all_polls"] = dict(discovery_sources)
    report["discovery_sources_last_poll"] = dict(Counter(p.get("_clean_source", "unknown") for p in raw))
    report["runtime_seconds"] = round(time.monotonic() - started, 3)
    report["run"] = {"id": os.environ.get("GITHUB_RUN_ID"),
                     "event": os.environ.get("GITHUB_EVENT_NAME"),
                     "sha": execution_sha(), "completed_at": utcnow()}
    report["previous_run"] = previous_run
    report["gap_since_previous_run_seconds"] = (
        round(first_poll_started_at - datetime.fromisoformat(previous_run["completed_at"]).timestamp(), 1)
        if previous_run.get("completed_at") else None)
    state["last_run"] = report["run"]
    save_json(STATE_FILE, state)
    save_json(REPORT_FILE, report)
    print("BRAIN_CLEAN_V1 " + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()


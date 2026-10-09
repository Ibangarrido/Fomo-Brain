"""Prospective observations, never a wallet or reconstructed trading return."""
import json
import math
import os
from datetime import datetime, timezone

FILE = "fomo_opportunity_audit_r1.json"
LIMIT = 500
HORIZON_SECONDS = 72 * 3600
MANUAL = {
    ("solana", "64oAuE88tNP7KsSyaiJTKGP4sWmLMFGWLUs9eBTLYgCp"),
    ("solana", "EkFRff9a2jKztJHML1LG9FRmEkPJDR6XAYp3uCPdpump"),
}
DECISIONS = {}


def begin_cycle():
    DECISIONS.clear()


def record_decisions(label, notes):
    for note in notes:
        if note.startswith("DESCARTE ") and " | " in note:
            key, reason = note[9:].split(" | ", 1)
            DECISIONS.setdefault(key, {})[label] = reason


def read():
    if not os.path.exists(FILE):
        return {"version": 1, "tokens": {}, "capacity_skips": 0}
    with open(FILE) as handle:
        state = json.load(handle)
    if state.get("version") != 1 or not isinstance(state.get("tokens"), dict):
        raise ValueError("Auditoria incompatible; conservar archivo, no reiniciar")
    return state


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def market_screen(snapshot, age_minutes, max_age):
    """Independent EARLY market gates, not full eligibility or a buy signal."""
    checks = [
        (snapshot["liquidity"], lambda v: v >= 20000, "liquidity_20000"),
        (snapshot["buy_ratio5m"], lambda v: v >= .60, "buy_count_60pct"),
        (snapshot["trades5m"], lambda v: v >= 40, "trades5m_40"),
        (snapshot["change5m"], lambda v: 2 <= v <= 60, "momentum5m_2_60"),
        (snapshot["change1h"], lambda v: v <= 150, "change1h_max150"),
        (age_minutes, lambda v: 2 <= v <= max_age, "pair_age_2_" + str(max_age)),
    ]
    return {name: "UNKNOWN" if value is None else "PASS" if predicate(value) else "FAIL"
            for value, predicate, name in checks}


def watch_targets(now=None):
    now = now or datetime.now(timezone.utc)
    state = read()
    active = []
    for row in state["tokens"].values():
        age = (now - datetime.fromisoformat(row["first"]["received_at"])).total_seconds()
        if 0 <= age < HORIZON_SECONDS + 24 * 3600 and not row.get("complete"):
            active.append(row)
    # Rotate regardless of quote failures or performance; dead quotes cannot
    # monopolize every monitoring slot.
    targets = sorted((r["chain"], r["address"]) for r in active
                     if (r["chain"], r["address"]) not in MANUAL)
    start = state.get("watch_cursor", 0) % len(targets) if targets else 0
    return sorted(MANUAL) + (targets[start:] + targets[:start])[:10]


def observe(pairs, sources, now=None, discovery_rejections=()):
    now = now or datetime.now(timezone.utc)
    state = read()
    rows = state["tokens"]
    selected = {}
    for pair in pairs.values():
        chain = pair.get("chainId")
        address = (pair.get("baseToken") or {}).get("address")
        price = number(pair.get("priceUsd"))
        liquidity = number((pair.get("liquidity") or {}).get("usd"))
        if not chain or not address or not pair.get("pairAddress") or price is None or price <= 0:
            continue
        key = chain + ":" + address
        old = selected.get(key)
        if old is None or (liquidity or 0) > (number((old.get("liquidity") or {}).get("usd")) or 0):
            selected[key] = pair
    # Fixed ordering, independent of later performance or the ranking score.
    for key, pair in sorted(selected.items()):
        chain, address = pair["chainId"], pair["baseToken"]["address"]
        liquidity = number((pair.get("liquidity") or {}).get("usd"))
        cap = number(pair.get("marketCap") or pair.get("fdv"))
        manual = (chain, address) in MANUAL
        if key not in rows:
            if not manual and not (liquidity is not None and liquidity >= 10000
                                   and cap is not None and 0 < cap <= 2000000):
                continue
            if len(rows) >= LIMIT:
                state["capacity_skips"] += 1
                continue
        m5 = (pair.get("txns") or {}).get("m5") or {}
        buys, sells = number(m5.get("buys")), number(m5.get("sells"))
        created = number(pair.get("pairCreatedAt"))
        age_minutes = (now.timestamp() - created / 1000) / 60 if created is not None and created > 0 else None
        snapshot = {"received_at": now.isoformat(), "price": number(pair["priceUsd"]),
                    "pair": pair["pairAddress"], "market_cap": cap, "liquidity": liquidity,
                    "buys5m": buys, "sells5m": sells,
                    "trades5m": buys + sells if buys is not None and sells is not None else None,
                    "pair_age_minutes": age_minutes,
                    "buy_ratio5m": buys / (buys + sells) if buys is not None and sells is not None and buys + sells > 0 else None,
                    "change5m": number((pair.get("priceChange") or {}).get("m5")),
                    "change1h": number((pair.get("priceChange") or {}).get("h1")),
                    "sources": sorted(sources.get((chain, pair["pairAddress"]), [])),
                    "entry_rejections": dict(DECISIONS.get(key, {})),
                    "discovery_rejections": sorted({r["reason"] for r in discovery_rejections
                        if r.get("chain") == chain and r.get("address") == address
                        and r.get("pair") == pair["pairAddress"]}),
                    "data_freshness": "UNKNOWN", "execution_verified": False}
        snapshot["early_market_screens"] = {str(age): market_screen(snapshot, age_minutes, age)
                                            for age in (60, 1440)}
        snapshot["screen_scope"] = "Independent market gates only; excludes score, wallet risk, security, confirmation and executable quotes; not entry eligibility."
        if key not in rows:
            rows[key] = {"chain": chain, "address": address,
                         "symbol": pair["baseToken"].get("symbol"),
                         "cohort": "manual_after_event" if manual else "automatic_prospective",
                         "first": snapshot, "last": snapshot, "peak": snapshot,
                         "observations": 0, "pair_changes": 0, "max_observation_gap_seconds": 0}
        row = rows[key]
        if row.get("complete"):
            continue
        gap = (now - datetime.fromisoformat(row["last"]["received_at"])).total_seconds()
        if gap < 0:
            raise ValueError("Observaciones fuera de orden; no sobrescribir")
        row["max_observation_gap_seconds"] = max(row["max_observation_gap_seconds"], gap)
        row["pair_changes"] += snapshot["pair"] != row["last"]["pair"]
        row["last"] = snapshot
        row["observations"] += 1
        if snapshot["price"] > row["peak"]["price"]:
            row["peak"] = snapshot
        row["observed_price_change_pct"] = (snapshot["price"] / row["first"]["price"] - 1) * 100
        row["observed_peak_change_pct"] = (row["peak"]["price"] / row["first"]["price"] - 1) * 100
        row["observed_drawdown_from_peak_pct"] = (snapshot["price"] / row["peak"]["price"] - 1) * 100
        elapsed = (now - datetime.fromisoformat(row["first"]["received_at"])).total_seconds()
        if elapsed >= HORIZON_SECONDS:
            row["complete"] = True
            row["completion"] = "first received observation after 72h; not exact horizon price"
    state["last_cycle_at"] = now.isoformat()
    state["watch_cursor"] = state.get("watch_cursor", 0) + 10
    state["limitations"] = "Received market snapshots; freshness unknown; sampled peaks; gaps and pair changes recorded; no trades, costs or net return. Manual cases excluded from automatic cohort. Missing quotes never become zero. Capacity bounded; skips counted."
    with open(FILE + ".tmp", "w") as handle:
        json.dump(state, handle, indent=2, allow_nan=False)
    os.replace(FILE + ".tmp", FILE)
    print("AUDITORIA OPORTUNIDADES " + json.dumps({"tracked": len(rows), "capacity_skips": state["capacity_skips"],
          "observed_this_cycle": sum(k in selected for k in rows), "no_trading_return": True}))
    for chain, address in sorted(MANUAL):
        row = rows.get(chain + ":" + address)
        if row:
            print("ESTUDIO OPORTUNIDAD " + json.dumps({k: row[k] for k in ("chain", "address", "symbol", "cohort", "first", "last", "observed_price_change_pct", "observed_peak_change_pct", "observed_drawdown_from_peak_pct")}, allow_nan=False))

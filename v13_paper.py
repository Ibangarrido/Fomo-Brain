"""Prospective price-model experiment; no wallet, order, or executable quote.

EUR/USD fixed at 1; modeled 3% cost on each side; gas/MEV excluded.
Stops execute only at the next valid observed price, never at an invented level.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from v13_hunter import finite

SCHEMA = "v13-paper-r1"


def initial_state():
    return {"schema": SCHEMA, "cash_eur": 100.0, "reserve_eur": 0.0,
            "positions": [], "closed": [], "last_at": None}


def stamp(value):
    try:
        t = datetime.fromisoformat(value)
        return t if t.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def key(row):
    return row.get("chain"), row.get("address"), row.get("pair")


def usable(row):
    price, liquidity = finite(row.get("price_usd")), finite(row.get("liquidity_usd"))
    return bool(price is not None and price > 0 and liquidity is not None and liquidity >= 20000)


def advance(state, rows, history, now):
    """Fail closed on bad state; never reset an existing portfolio on read errors."""
    s = deepcopy(state)
    if (s.get("schema") != SCHEMA or
        any(finite(s.get(k)) is None or s[k] < 0 for k in ("cash_eur", "reserve_eur")) or
        not isinstance(s.get("positions"), list) or not isinstance(s.get("closed"), list)):
        raise ValueError("Invalid V13 paper state; refusing reset")
    if s.get("last_at") and (stamp(s["last_at"]) is None or stamp(s["last_at"]) >= now):
        raise ValueError("V13 paper clock must advance")
    identities = set()
    for pos in s["positions"]:
        identity = key(pos)[:2]
        if (not all(isinstance(v, str) and v for v in key(pos)) or
            identity in identities or stamp(pos.get("opened_at")) is None or
            stamp(pos["opened_at"]) > now or
            any(finite(pos.get(k)) is None or pos[k] <= 0
                for k in ("quantity", "cost_eur", "entry_price_usd", "peak_usd")) or
            pos["cost_eur"] > 10):
            raise ValueError("Invalid V13 open position")
        identities.add(identity)
    if len(identities) > 2:
        raise ValueError("Invalid V13 position count")
    current = {key(r): r for r in rows}
    events, diagnostics, exited = [], [], set()
    unknown = 0
    marked = 0.0
    remaining = []
    for pos in s["positions"]:
        row = current.get(key(pos))
        if not row or not usable(row):
            unknown += 1
            remaining.append(pos)
            continue
        price = row["price_usd"]
        pos["peak_usd"] = max(pos["peak_usd"], price)
        value = pos["quantity"] * price * .97
        pnl = value - pos["cost_eur"]
        age = (now - stamp(pos["opened_at"])).total_seconds() / 60
        reason = ("STOP_OBSERVED" if value <= pos["cost_eur"] * .90 else
                  "TAKE_PROFIT_OBSERVED" if value >= pos["cost_eur"] * 1.30 else
                  "TRAILING_OBSERVED" if pos["peak_usd"] >= pos["entry_price_usd"] * 1.20 and price <= pos["peak_usd"] * .85 else
                  "TIME_EXIT_OBSERVED" if age >= 90 else None)
        if reason:
            reserve = max(0, pnl) * .5
            s["cash_eur"] += value - reserve
            s["reserve_eur"] += reserve
            event = dict(pos, closed_at=now.isoformat(), exit_price_usd=price,
                         proceeds_eur=value, net_pnl_eur=pnl, reason=reason)
            s["closed"].append(event)
            events.append(dict(event, side="SELL_MODEL"))
            exited.add(key(pos)[:2])
        else:
            marked += value
            remaining.append(pos)
    s["positions"] = remaining
    # Several pools cannot create several entries in one token.
    held = {key(p)[:2] for p in remaining}
    cooldown = {key(p)[:2] for p in s["closed"]
                if stamp(p["closed_at"]) >= now - timedelta(hours=24)}
    for row in sorted(rows, key=lambda r: r.get("trades_5m") or 0, reverse=True):
        if not (row.get("market_gates_pass") or row.get("mature_watch")):
            continue
        reason = None
        if not usable(row) or (finite(row.get("volume_5m_usd")) or 0) < 1500:
            reason = "INVALID_PRICE_OR_LOW_VOLUME"
        prior = [r for r in history if key(r) == key(row) and stamp(r.get("received_at")) is not None
                 and now-timedelta(minutes=30) <= stamp(r["received_at"]) <= now-timedelta(minutes=5)
                 and usable(r) and (finite(r.get("volume_5m_usd")) or 0) >= 1500
                 and (r.get("market_gates_pass") or r.get("mature_watch"))]
        previous = max(prior, key=lambda r: stamp(r["received_at"])) if prior else None
        if reason is None and previous is None:
            reason = "AWAITING_SECOND_QUALIFIED_SAME_POOL_OBSERVATION"
        if reason is None and not 1 <= (row["price_usd"] / previous["price_usd"] - 1) * 100 <= 12:
            reason = "CONFIRMATION_CHANGE_OUTSIDE_1_12PCT"
        token = key(row)[:2]
        if token in held or token in cooldown or token in exited:
            reason = "HELD_OR_24H_COOLDOWN"
        if len(s["positions"]) >= 2 or s["cash_eur"] < 10:
            reason = "POSITION_OR_CASH_LIMIT"
        # Use only known current liquidation-model value for the drawdown gate.
        if s["cash_eur"] + s["reserve_eur"] + marked <= 75:
            reason = "CAPITAL_FLOOR"
        diagnostics.append({"chain": row["chain"], "address": row["address"],
                            "pair": row["pair"], "blocker": reason})
        if reason:
            continue
        position = {k: row.get(k) for k in ("chain", "address", "pair", "symbol")}
        position.update(opened_at=now.isoformat(), cost_eur=10.0,
                        quantity=10 / (row["price_usd"] * 1.03),
                        entry_price_usd=row["price_usd"], peak_usd=row["price_usd"])
        s["cash_eur"] -= 10
        s["positions"].append(position)
        marked += position["quantity"] * row["price_usd"] * .97
        held.add(token)
        events.append(dict(position, side="BUY_MODEL"))
    s["last_at"] = now.isoformat()
    # Retrospective accounting diagnostics: never interpreted as executable fills.
    recent_closed = s["closed"][-30:]
    closed_audit = []
    for closed in recent_closed:
        entry, exit_price = finite(closed.get("entry_price_usd")), finite(closed.get("exit_price_usd"))
        cost, proceeds = finite(closed.get("cost_eur")), finite(closed.get("proceeds_eur"))
        if not entry or not exit_price or cost is None or proceeds is None:
            continue
        gross_price_change = (exit_price / entry - 1) * 100
        net_return = (proceeds / cost - 1) * 100 if cost else None
        closed_audit.append({"chain": closed.get("chain"), "address": closed.get("address"),
                             "symbol": closed.get("symbol"), "reason": closed.get("reason"),
                             "gross_price_change_pct": round(gross_price_change, 2),
                             "net_modeled_return_pct": round(net_return, 2) if net_return is not None else None,
                             "stop_gap_beyond_10pct_points": round(max(0, -10-net_return), 2)
                             if closed.get("reason") == "STOP_OBSERVED" and net_return is not None else None,
                             "entry_to_exit_minutes": round((stamp(closed["closed_at"])-stamp(closed["opened_at"])).total_seconds()/60, 1)
                             if stamp(closed.get("closed_at")) and stamp(closed.get("opened_at")) else None})
    summary = {"schema": SCHEMA, "mode": "prospective_price_model_only",
               "execution_verified": False, "cash_eur": round(s["cash_eur"], 4),
               "reserve_eur": round(s["reserve_eur"], 4),
               "open_positions": len(s["positions"]), "unknown_positions": unknown,
               "modeled_equity_eur": None if unknown else round(s["cash_eur"] + s["reserve_eur"] + marked, 4),
               "modeled_realized_pnl_eur": round(sum(p["net_pnl_eur"] for p in s["closed"]), 4),
               "events": events, "entry_checks": diagnostics, "recent_closed_audit": closed_audit,
               "assumptions": "Fixed EUR/USD=1; 3% each side; gas/MEV excluded; no sell-route verification; stops only at observed prices; no monitoring between runs"}
    return s, summary

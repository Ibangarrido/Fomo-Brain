"""Research-only cross-run recovery radar. Never opens paper or real positions."""
from datetime import datetime, timezone
from itertools import combinations
import math


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _timestamp(row):
    try:
        value = datetime.fromisoformat(str(row.get("received_at") or row.get("hora")))
        return value.astimezone(timezone.utc) if value.utcoffset() is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _blockers(token):
    """Independent gates, not a complete or executable entry decision."""
    checks = (
        ("buy_ratio_below_60pct", _number(token.get("buyRatio5m")), .60),
        ("liquidity_below_20000", _number(token.get("liquidity")), 20000),
        ("trades5m_below_40", _number(token.get("trades5m")), 40),
        ("score_below_5", _number(token.get("score")), 5),
    )
    blocked = [name for name, value, minimum in checks if value is None or value < minimum]
    change = _number(token.get("change1h"))
    if change is None or change > 150:
        blocked.append("change1h_unknown_or_above_150pct")
    momentum = _number(token.get("change5m"))
    if momentum is None or momentum <= 0:
        blocked.append("nonpositive_5m_momentum")
    return blocked


def scan(ranking, history, *, max_age_minutes=120):
    """Observe impulse -> 8-35% pullback -> two successive recoveries.

    Permit at most ONE intermediate quote between each selected turning point.
    This repairs missed patterns caused by extra sampling, without selecting
    arbitrary distant highs/lows or treating provider receipts as trade times.
    No wallet, order, entry gate or balance is modified.
    """
    now = datetime.now(timezone.utc)
    by_pair = {}
    for row in history:
        if not isinstance(row, dict):
            continue
        key = (row.get("chain"), row.get("address"), row.get("pair"))
        at = _timestamp(row)
        price = _number(row.get("price"))
        if not all(key) or at is None or price is None or price <= 0:
            continue
        if not 0 <= (now - at).total_seconds() <= max_age_minutes * 60:
            continue
        by_pair.setdefault(key, {})[at] = row

    results = []
    for token in ranking:
        key = (token.get("chain"), token.get("address"), token.get("pair"))
        at = _timestamp(token)
        if not all(key) or at is None or _number(token.get("price")) in (None, 0):
            continue
        distinct = dict(by_pair.get(key, {}))
        distinct[at] = token
        rows = [distinct[t] for t in sorted(distinct)][-12:]
        if len(rows) < 5 or rows[-1] is not token:
            continue
        # Four earlier turning points + latest. Each selected pair may skip
        # at most one intermediate quote; avoid hindsight over long histories.
        n = len(rows)
        matches = []
        for indices in combinations(range(n - 1), 4):
            chosen = (*indices, n - 1)
            if any(b - a > 2 for a, b in zip(chosen, chosen[1:])):
                continue
            selected = [rows[i] for i in chosen]
            stamps = [_timestamp(row) for row in selected]
            gaps = [(b - a).total_seconds() / 60 for a, b in zip(stamps, stamps[1:])]
            if not all(.5 <= gap <= 30 for gap in gaps):
                continue
            prices = [_number(row.get("price")) for row in selected]
            liq = [_number(row.get("liquidity")) for row in selected]
            if any(v is None or v <= 0 for v in prices + liq):
                continue
            pullback = (prices[1] - prices[2]) / prices[1]
            if not (prices[1] > prices[0] and .08 <= pullback <= .35
                    and prices[2] < prices[3] < prices[4]
                    and prices[4] <= prices[1] * 1.30
                    and liq[4] >= liq[2] * .90):
                continue
            matches.append((chosen, pullback, prices))
        if not matches:
            continue
        # Prefer the most recent impulse/peak, not the most profitable-looking
        # retrospectively selected pattern.
        chosen, pullback, prices = max(matches, key=lambda m: m[0][1])
        ratio = _number(token.get("buyRatio5m"))
        blockers = _blockers(token)
        results.append({
            "chain": key[0], "address": key[1], "pair": key[2],
            "symbol": token.get("symbol"),
            "detected_at": at.isoformat(),
            "selected_observations": 5,
            "intermediate_quotes_skipped": sum(b-a-1 for a, b in zip(chosen, chosen[1:])),
            "pullback_pct": round(pullback * 100, 2),
            "recovery_pct": round((prices[4] / prices[2] - 1) * 100, 2),
            "buy_ratio_pct": round(ratio * 100, 1) if ratio is not None else None,
            "below_60pct_buy_gate": ratio is not None and ratio < .60,
            "independent_entry_blockers": blockers,
            "status": "OBSERVED_PATTERN_ONLY",
            "execution_verified": False,
            "future_outcome_verified": False,
        })
    return results

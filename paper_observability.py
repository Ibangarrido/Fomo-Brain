"""Paper-only observability for rejected candidates and simulated executions.

This module never sends orders or mutates portfolio histories.
"""
from datetime import datetime, timezone
from math import isfinite


def _number(value):
    try:
        if isinstance(value, bool):
            return None
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if isfinite(result) and result > 0 else None


def observe_rejection(candidate_id, rejected_at, reference_price, observations):
    """Measure forward price changes; missing quotes remain unknown, never zero."""
    if not isinstance(rejected_at, datetime) or rejected_at.tzinfo is None:
        raise ValueError("rejected_at must be timezone-aware")
    base = _number(reference_price)
    if not candidate_id or base is None:
        raise ValueError("candidate_id and positive reference_price required")
    result = {"candidate_id": candidate_id, "rejected_at": rejected_at.isoformat(),
              "reference_price": base, "forward_returns_pct": {}}
    for minutes in (5, 15, 30, 60):
        target = rejected_at.timestamp() + minutes * 60
        eligible = []
        for observation in observations:
            stamp = observation.get("timestamp")
            price = _number(observation.get("price"))
            if isinstance(stamp, datetime) and stamp.tzinfo is not None and price is not None:
                if target <= stamp.timestamp() <= target + 120:
                    eligible.append((stamp.timestamp(), price))
        if eligible:
            _, price = min(eligible)
            result["forward_returns_pct"][str(minutes)] = round((price / base - 1) * 100, 6)
        else:
            result["forward_returns_pct"][str(minutes)] = None
    return result


def net_paper_exit(quantity, entry_price, exit_price, entry_fee=0, exit_fee=0, network_cost=0):
    """Net P&L of a hypothetical fully quoted round trip; no execution."""
    values = [quantity, entry_price, exit_price]
    if any(_number(x) is None for x in values):
        return {"status": "unknown", "net_pnl": None}
    quantity, entry_price, exit_price = map(float, values)
    costs = [entry_fee, exit_fee, network_cost]
    if any(not isinstance(x, (int, float)) or not isfinite(x) or x < 0 for x in costs):
        return {"status": "unknown", "net_pnl": None}
    return {"status": "quoted_simulation",
            "net_pnl": round(quantity * (exit_price - entry_price) - sum(costs), 8)}

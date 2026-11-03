"""Fail-closed, read-only quality audit of Clean V1 state artifacts.

No ledger mutation, pricing, or trading. Missing fields are reported, never inferred.
"""
import math

WATCH = ("MARVIN", "REGRET", "paws")
FIELDS = ("quote_timestamp", "liquidity_usd", "route_status", "retention_reason")

def _number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0

def audit_position(position):
    """Audit normalized monitoring records; require explicit missing reasons."""
    if not isinstance(position, dict):
        return {"complete": False, "missing": list(FIELDS), "realizable_value_eur": None}
    missing = []
    for field in FIELDS:
        value = position.get(field)
        if field == "liquidity_usd":
            valid = _number(value)
        else:
            valid = isinstance(value, str) and bool(value.strip())
        if not valid and not (isinstance(position.get(field + "_missing_reason"), str)
                              and position[field + "_missing_reason"].strip()):
            missing.append(field)
    return {"complete": not missing, "missing": missing,
            "realizable_value_eur": position.get("realizable_value_eur")
            if position.get("execution_verified") is True and
            _number(position.get("realizable_value_eur")) else None}

def audit_state(records):
    """Input is normalized records, keyed by exact watch symbol."""
    if not isinstance(records, dict):
        records = {}
    positions = {symbol: audit_position(records.get(symbol)) for symbol in WATCH}
    complete = sum(p["complete"] for p in positions.values())
    return {"positions": positions, "coverage_pct": round(100 * complete / len(WATCH), 2),
            "complete": complete == len(WATCH),
            "scope": "PAPER_ONLY_NO_LEDGER_MUTATION"}

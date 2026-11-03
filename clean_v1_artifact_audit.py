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

def audit_isolated_ledger(state):
    """Normalize exact-symbol isolated holdings without asserting exits or prices."""
    from datetime import datetime, timezone
    records = {}
    for pos in state.get("isolated_positions", {}).values():
        symbol = str(pos.get("symbol", "")).strip()
        matches = [s for s in WATCH if s.upper() == symbol.upper()]
        if not matches:
            continue
        symbol = matches[0]
        # Duplicate tickers cannot safely be merged or attributed.
        if symbol in records:
            records[symbol] = {"route_status": "UNVERIFIED",
                               "quote_timestamp_missing_reason": "AMBIGUOUS_DUPLICATE_SYMBOL",
                               "liquidity_usd_missing_reason": "AMBIGUOUS_DUPLICATE_SYMBOL",
                               "retention_reason_missing_reason": "AMBIGUOUS_DUPLICATE_SYMBOL"}
            continue
        monitoring = pos.get("monitoring_audit") or {}
        ts = monitoring.get("last_observed_ts")
        quote_ts = (datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    if _number(ts) and ts > 0 else None)
        liquidity = monitoring.get("liquidity_usd")
        records[symbol] = {
            "status": pos.get("isolation_status", "UNKNOWN"),
            "quote_status": monitoring.get("quote_status", "NOT_OBSERVED"),
            "quote_timestamp": quote_ts,
            "quote_timestamp_missing_reason": None if quote_ts else "NO_VALID_OBSERVATION",
            "liquidity_usd": liquidity if _number(liquidity) else None,
            "liquidity_usd_missing_reason": None if _number(liquidity) else "NO_VALID_OBSERVATION",
            "route_status": "UNVERIFIED",
            "retention_reason": pos.get("isolation_reason"),
            "retention_reason_missing_reason": None if pos.get("isolation_reason") else "NOT_RECORDED",
            "execution_verified": False, "realizable_value_eur": None,
            "indicative_price_usd": monitoring.get("price_usd"),
        }
    return {"audit": audit_state(records), "records": records,
            "note": "Coverage means documented or explicitly unknown; not verified exit liquidity"}

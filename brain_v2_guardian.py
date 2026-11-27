"""PAPER ONLY: classify risk, never mutate a ledger or execute a sale."""
import math

def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

def assess(entry, price, quote_age, liquidity, route_verified, *, max_age=60, min_liquidity=5000, stop_pct=20):
    if not number(entry) or entry <= 0:
        return "INVALID_ENTRY"
    if not number(price) or price < 0:
        return "QUARANTINE_MISSING_QUOTE"
    if not number(quote_age) or not 0 <= quote_age <= max_age:
        return "QUARANTINE_STALE_QUOTE"
    if price == 0:
        return "QUARANTINE_ZERO_QUOTE"
    if not number(liquidity) or liquidity < min_liquidity or route_verified is not True:
        return "QUARANTINE_UNVERIFIED_EXIT"
    if (price / entry - 1) * 100 <= -stop_pct:
        return "PAPER_EXIT_CANDIDATE"
    return "MONITOR"

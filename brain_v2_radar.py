"""PAPER ONLY watchlist classifier; no orders or ledger writes."""
import math

def assess(volume_5m, previous_volume_5m, buyers_5m, previous_buyers_5m,
           liquidity, change_5m_pct, change_1h_pct, quote_age_seconds):
    values = (volume_5m, previous_volume_5m, buyers_5m, previous_buyers_5m,
              liquidity, change_5m_pct, change_1h_pct, quote_age_seconds)
    if any(isinstance(x, bool) or not isinstance(x, (int,float)) or not math.isfinite(x) for x in values):
        return "UNKNOWN_DATA"
    if min(volume_5m, previous_volume_5m, buyers_5m, previous_buyers_5m, liquidity, quote_age_seconds) < 0:
        return "INVALID_DATA"
    if quote_age_seconds > 60:
        return "STALE_DATA"
    if liquidity < 5000:
        return "LOW_LIQUIDITY"
    if change_1h_pct >= 150 or change_5m_pct >= 30:
        return "LATE_SPIKE"
    if previous_volume_5m < 100 or previous_buyers_5m < 5:
        return "INSUFFICIENT_BASELINE"
    if (volume_5m >= 500 and volume_5m >= 2 * previous_volume_5m
        and buyers_5m >= 1.5 * previous_buyers_5m and 0 < change_5m_pct < 30
        and 0 <= change_1h_pct < 150):
        return "EARLY_WATCH"
    return "MONITOR"

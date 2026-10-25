"""Paper-only candle pattern research. No trade authorization or network access."""
from math import isfinite


def analyze_candles(candles, *, min_liquidity_usd=10000):
    """Chronological closed OHLCV candles, oldest first; never infer intrabar fills."""
    if len(candles) < 5:
        return {"status": "INSUFFICIENT_DATA", "entry_authorized": False}
    clean = []
    for candle in candles:
        try:
            o, h, l, c, v = (float(candle[k]) for k in ("open", "high", "low", "close", "volume"))
            liquidity = float(candle["liquidity_usd"])
        except (KeyError, TypeError, ValueError):
            return {"status": "INVALID_DATA", "entry_authorized": False}
        if not all(isfinite(x) for x in (o, h, l, c, v, liquidity)) or min(o, l, c) <= 0 or h < max(o, c, l) or l > min(o, c) or v < 0 or liquidity < 0:
            return {"status": "INVALID_DATA", "entry_authorized": False}
        clean.append((o, h, l, c, v, liquidity))
    previous = clean[-5:-2]
    last_two = clean[-2:]
    two_bullish = all(c > o for o, _, _, c, _, _ in last_two)
    prior_peak = max(x[1] for x in previous)
    recent_trough = min(x[2] for x in clean[-4:])
    prior_volume = sum(x[4] for x in previous) / 3
    last_volume = sum(x[4] for x in last_two) / 2
    liquidity_now = clean[-1][5]
    liquidity_before = clean[-3][5]
    liquidity_drop_pct = 100 * (1 - liquidity_now / liquidity_before) if liquidity_before > 0 else None
    volume_confirmation = prior_volume > 0 and last_volume >= 1.2 * prior_volume
    recovered = two_bullish and clean[-1][3] > prior_peak and volume_confirmation
    liquidity_risk = (liquidity_now < min_liquidity_usd or liquidity_drop_pct is None or liquidity_drop_pct >= 30)
    return {
        "status": "LIQUIDITY_RISK" if liquidity_risk else "RECOVERY_RESEARCH" if recovered else "NO_PATTERN",
        "two_bullish_closed_candles": two_bullish,
        "breaks_prior_three_candle_high": clean[-1][3] > prior_peak,
        "volume_confirmation": volume_confirmation,
        "liquidity_drop_pct": liquidity_drop_pct,
        "recent_trough": recent_trough,
        "entry_authorized": False,
        "execution_verified": False,
        "scope": "research only; requires authentic timestamped OHLCV and pool liquidity",
    }

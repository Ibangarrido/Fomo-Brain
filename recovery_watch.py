"""RECOVERY WATCH: observational, paper-only second-chance signal detector.

Input: chronological snapshots of one token with timestamp (ISO UTC), price,
liquidity_usd, buy_ratio, volume_5m and optionally trades_5m.
No orders, keys, wallets, or network access. Missing data never becomes a signal.
"""
from datetime import datetime, timezone
from math import isfinite

MIN_PULLBACK_PCT = 8.0
MIN_BUY_RATIO = 0.60
MIN_RECOVERY_CANDLES = 2
MIN_LIQUIDITY_USD = 10_000
WATCH_MINUTES = 60


def _num(value):
    try:
        number = float(value)
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def evaluate_recovery(snapshots, discarded_at):
    """Return auditable signal or rejection; all thresholds are experimental.

    A snapshot is not a candle. Two consecutive rising observations are only
    a proxy; use actual OHLCV candles before describing candle confirmation.
    """
    start = _time(discarded_at)
    if start is None:
        return {"status": "NO_DATA", "reason": "invalid_discard_timestamp"}
    valid = []
    for item in snapshots:
        stamp = _time(item.get("timestamp"))
        price = _num(item.get("price"))
        liquidity = _num(item.get("liquidity_usd"))
        ratio = _num(item.get("buy_ratio"))
        volume = _num(item.get("volume_5m"))
        if (stamp is None or price is None or price <= 0 or
                liquidity is None or ratio is None or volume is None):
            continue
        if start <= stamp <= start.replace() + __import__("datetime").timedelta(minutes=WATCH_MINUTES):
            valid.append((stamp, price, liquidity, ratio, volume))
    valid.sort(key=lambda item: item[0])
    if len(valid) < 4:
        return {"status": "NO_DATA", "reason": "insufficient_valid_observations",
                "observations": len(valid)}
    peak = valid[0][1]
    trough = peak
    rises = 0
    pullback_seen = False
    for index, (stamp, price, liquidity, ratio, volume) in enumerate(valid):
        if price > peak and not pullback_seen:
            peak = price
        if not pullback_seen:
            trough = min(trough, price)
            if peak > 0 and (peak - trough) / peak * 100 >= MIN_PULLBACK_PCT:
                pullback_seen = True
        if index and price > valid[index - 1][1]:
            rises += 1
        else:
            rises = 0
        if (pullback_seen and rises >= MIN_RECOVERY_CANDLES and
                liquidity >= MIN_LIQUIDITY_USD and ratio >= MIN_BUY_RATIO and
                volume > valid[index - 1][4]):
            return {"status": "PAPER_SIGNAL", "timestamp": stamp.isoformat(),
                    "price": price, "pullback_pct": round((peak-trough)/peak*100, 3),
                    "observations": len(valid), "reason": "recovery_confirmed"}
    return {"status": "WATCH", "reason": "no_confirmed_recovery",
            "observations": len(valid)}

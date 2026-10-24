"""Research-only cross-run pattern diagnostics; never authorizes paper or real entries."""
from datetime import datetime, timezone
import math


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _timestamp(row):
    try:
        result = datetime.fromisoformat(str(row.get('received_at') or row.get('hora')))
        return result.astimezone(timezone.utc) if result.utcoffset() is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def scan(ranking, history, *, max_age_minutes=120):
    """Look for peak -> 8-35% pullback -> two price recoveries on exact pair.

    Reads only observed snapshots, never reconstructs intra-run candles or fills.
    """
    now = datetime.now(timezone.utc)
    by_pair = {}
    for row in history:
        if not isinstance(row, dict):
            continue
        key = (row.get('chain'), row.get('address'), row.get('pair'))
        when = _timestamp(row)
        price = _number(row.get('price'))
        if not all(key) or when is None or price is None or price <= 0:
            continue
        if not 0 <= (now - when).total_seconds() <= max_age_minutes * 60:
            continue
        by_pair.setdefault(key, {})[when] = row
    results = []
    for token in ranking:
        key = (token.get('chain'), token.get('address'), token.get('pair'))
        when = _timestamp(token)
        price = _number(token.get('price'))
        if not all(key) or when is None or price is None or price <= 0:
            continue
        rows = sorted((*by_pair.get(key, {}).values(), token), key=_timestamp)
        # Ignore duplicate timestamps and require five independently received quotes.
        distinct = {}
        for row in rows:
            distinct[_timestamp(row)] = row
        rows = [distinct[t] for t in sorted(distinct)][-5:]
        if len(rows) != 5 or rows[-1] is not token:
            continue
        times = list(map(_timestamp, rows))
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(times, times[1:])]
        if not all(0.5 <= gap <= 30 for gap in gaps):
            continue
        p = [_number(row.get('price')) for row in rows]
        liq = [_number(row.get('liquidity')) for row in rows]
        if any(x is None or x <= 0 for x in p + liq):
            continue
        pullback = (p[1] - p[2]) / p[1]
        if not (p[1] > p[0] and .08 <= pullback <= .35 and
                p[2] < p[3] < p[4] and p[4] <= p[1] * 1.30 and
                liq[4] >= liq[2] * .90):
            continue
        change1h = _number(token.get('change1h'))
        if change1h is None or change1h > 150:
            continue
        ratio = _number(token.get('buyRatio5m'))
        results.append({
            'chain': key[0], 'address': key[1], 'symbol': token.get('symbol'),
            'pullback_pct': round(pullback * 100, 2),
            'recovery_pct': round((p[4] / p[2] - 1) * 100, 2),
            'buy_ratio_pct': round(ratio * 100, 1) if ratio is not None else None,
            'below_60pct_buy_gate': ratio is not None and ratio < .60,
            'status': 'OBSERVED_PATTERN_ONLY',
        })
    return results

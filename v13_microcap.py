"""Pre-impulse microcap research radar. Never authorizes trading.

Only uses timestamped snapshots collected before the current observation.
A candidate is NOT evidence of an impending pump or of safe liquidity.
"""
from datetime import datetime, timedelta, timezone
from v13_hunter import finite


def _stamp(value):
    try:
        t = datetime.fromisoformat(value)
        return t.astimezone(timezone.utc) if t.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def microcap_observation(row, previous=()):
    """Detect quiet microcaps beginning to wake, using strictly past observations."""
    result = dict(row)
    now = _stamp(row.get("received_at"))
    cap = finite(row.get("market_cap_usd"))
    liq = finite(row.get("liquidity_usd"))
    vol = finite(row.get("volume_5m_usd"))
    trades = finite(row.get("trades_5m"))
    buy_ratio = finite(row.get("buy_ratio_5m"))
    change5 = finite(row.get("change_5m_pct"))
    change1h = finite(row.get("change_1h_pct"))
    age = finite(row.get("pair_age_minutes"))
    result.update(microcap_research_only=True, microcap_history_sufficient=False,
                  microcap_watch=False, microcap_volume_multiple=None,
                  microcap_signal="HISTORIAL_INSUFICIENTE")
    if now is None:
        return result
    samples = []
    for old in previous:
        if any(old.get(k) != row.get(k) for k in ("chain", "address", "pair")):
            continue
        ts = _stamp(old.get("received_at"))
        v = finite(old.get("volume_5m_usd"))
        n = finite(old.get("trades_5m"))
        if ts is not None and now-timedelta(hours=3) <= ts <= now-timedelta(minutes=10) and v is not None and n is not None:
            samples.append((ts, v, n))
    samples.sort()
    # Distinct timestamps prevent duplicated snapshots from faking persistence.
    unique = {ts: (ts, v, n) for ts, v, n in samples}
    samples = sorted(unique.values())[-8:]
    enough = len(samples) >= 3 and (samples[-1][0]-samples[0][0]) >= timedelta(minutes=20)
    result["microcap_history_sufficient"] = enough
    if not enough:
        return result
    quiet = all(v <= 800 and n <= 12 for _, v, n in samples)
    avg = sum(v for _, v, _ in samples)/len(samples)
    multiple = vol/max(200, avg) if vol is not None else None
    result["microcap_volume_multiple"] = round(multiple, 2) if multiple is not None else None
    # Microcap research only: 5k liquidity is not necessarily executable at 10 EUR.
    basic = (cap is not None and 10000 <= cap <= 100000 and
             liq is not None and liq >= 5000 and age is not None and age >= 30 and
             change1h is not None and -20 <= change1h <= 40)
    emerging = (vol is not None and vol >= 1000 and trades is not None and trades >= 18 and
                buy_ratio is not None and buy_ratio >= .60 and
                change5 is not None and 0 <= change5 <= 15 and
                multiple is not None and multiple >= 2.5)
    result["microcap_watch"] = bool(quiet and basic and emerging)
    result["microcap_signal"] = ("MICROCAP_DESPERTAR_INVESTIGAR" if result["microcap_watch"] else
                                  "MICROCAP_SIN_CONFIRMACION")
    return result

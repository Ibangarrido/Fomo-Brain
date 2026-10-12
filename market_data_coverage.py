"""Conservative coverage audit for market observations; no orders or wallet access."""
from datetime import datetime, timezone
import math

REQUIRED = ("price", "liquidity_usd", "volume_5m_usd", "buys_5m", "sells_5m", "holders")
MAX_AGE_SECONDS = 90

def audit(observation, now=None):
    """Fail closed on absent, stale or malformed observations; never infer a fill."""
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    missing = []
    invalid = []
    for field in REQUIRED:
        value = observation.get(field)
        if value is None:
            missing.append(field)
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (field == "price" and value == 0):
            invalid.append(field)
    ts = observation.get("provider_timestamp")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts) or ts <= 0:
        freshness = "UNVERIFIED"
        age = None
    else:
        ts = ts / 1000 if ts >= 1e12 else ts
        age = now - ts
        freshness = "FUTURE" if age < -10 else "STALE" if age > MAX_AGE_SECONDS else "FRESH"
    return {"status": "COMPLETE_OBSERVATION" if not missing and not invalid and freshness == "FRESH" else "INCOMPLETE",
            "missing_fields": missing, "invalid_fields": invalid,
            "freshness": freshness, "age_seconds": round(age, 2) if age is not None else None,
            "exit_quote_verified": False, "paper_fill_authorized": False}

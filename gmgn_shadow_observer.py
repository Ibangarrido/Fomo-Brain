"""GMGN shadow observer: validate read-only trade events; never execute trades."""
import math
from datetime import datetime, timezone

REQUIRED = ("wallet", "chain", "tx_hash", "token_address", "side",
            "block_timestamp", "observed_at", "price_usd", "liquidity_usd")

def _finite_nonnegative(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)

def validate_trade_event(event, *, max_delay_seconds=120):
    """Return a validated observation or a rejection; never imply a fill."""
    if not isinstance(event, dict):
        return {"accepted": False, "reason": "INVALID_EVENT"}
    if any(not isinstance(event.get(k), str) or not event[k].strip()
           for k in ("wallet", "chain", "tx_hash", "token_address", "side")):
        return {"accepted": False, "reason": "MISSING_IDENTITY"}
    if event["side"].upper() not in ("BUY", "SELL"):
        return {"accepted": False, "reason": "INVALID_SIDE"}
    if not event.get("transaction_verified") is True:
        return {"accepted": False, "reason": "TRANSACTION_UNVERIFIED"}
    for k in ("block_timestamp", "observed_at", "price_usd", "liquidity_usd"):
        if not _finite_nonnegative(event.get(k)):
            return {"accepted": False, "reason": "INVALID_NUMERIC_" + k.upper()}
    delay = event["observed_at"] - event["block_timestamp"]
    if delay < 0 or delay > max_delay_seconds:
        return {"accepted": False, "reason": "STALE_OR_FUTURE_TRANSACTION"}
    if event["price_usd"] <= 0:
        return {"accepted": False, "reason": "INVALID_PRICE"}
    if event["liquidity_usd"] < 10000:
        return {"accepted": False, "reason": "INSUFFICIENT_LIQUIDITY"}
    return {"accepted": True, "mode": "SHADOW_READ_ONLY",
            "wallet": event["wallet"], "chain": event["chain"],
            "tx_hash": event["tx_hash"], "token_address": event["token_address"],
            "side": event["side"].upper(), "detection_delay_seconds": round(delay, 3),
            "observed_price_usd": event["price_usd"],
            "execution_verified": False, "realizable_proceeds_eur": None}

def observe(events):
    """Deduplicate by chain/transaction/token/side, preserve rejections."""
    seen = set()
    accepted, rejected = [], []
    for event in events:
        result = validate_trade_event(event)
        if not result["accepted"]:
            rejected.append(result["reason"])
            continue
        key = (result["chain"], result["tx_hash"], result["token_address"], result["side"])
        if key in seen:
            rejected.append("DUPLICATE_TRANSACTION")
            continue
        seen.add(key)
        accepted.append(result)
    return {"status": "SHADOW_READ_ONLY", "accepted": accepted,
            "rejected": rejected, "trade_executions": 0}

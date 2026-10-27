"""Research-only memecoin trap diagnostics from public market snapshots.

No orders, no wallet mutation, no claims of manipulation or executable exit.
"""
import math


def finite_nonnegative(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError):
        return None


def assess(pair):
    liquidity = finite_nonnegative((pair.get("liquidity") or {}).get("usd"))
    volume = finite_nonnegative((pair.get("volume") or {}).get("m5"))
    tx = (pair.get("txns") or {}).get("m5") or {}
    buys = finite_nonnegative(tx.get("buys"))
    sells = finite_nonnegative(tx.get("sells"))
    change = pair.get("priceChange") or {}
    try:
        change5 = float(change.get("m5"))
        if not math.isfinite(change5):
            change5 = None
    except (ValueError, TypeError):
        change5 = None
    flags = []
    unknown = []
    if liquidity is None:
        unknown.append("liquidity")
    elif liquidity < 20000:
        flags.append("thin_liquidity_under_20k_usd")
    if volume is None:
        unknown.append("volume_m5")
    if buys is None or sells is None:
        unknown.append("transactions_m5")
    if change5 is None:
        unknown.append("price_change_m5")
    if (volume is not None and liquidity is not None and liquidity > 0
            and volume / liquidity >= 3):
        flags.append("high_5m_turnover_relative_to_liquidity")
    if (change5 is not None and change5 <= -35
            and sells is not None and buys is not None and sells >= buys * 2
            and sells >= 10):
        flags.append("sharp_drop_with_sell_count_dominance")
    return {
        "mode": "research_only",
        "risk_flags": flags,
        "unknown_inputs": unknown,
        "liquidity_usd": liquidity,
        "volume_m5_usd": volume,
        "change_m5_pct": change5,
        "trade_count_buys_m5": buys,
        "trade_count_sells_m5": sells,
        "wallet_concentration": "not_available",
        "liquidity_withdrawals": "not_available",
        "executable_exit": "not_verified",
        "is_fraud_verdict": False,
        "scope": "Heuristic flags, not a prediction, manipulation finding or entry permission",
    }

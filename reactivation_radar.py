"""Research-only radar for reactivated older pairs. Never changes entry eligibility."""
from datetime import datetime, timezone
import math


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def scan(pairs, *, min_age_days=7, limit=10):
    """Snapshot older pairs BEFORE the >150%/h rejection.

    This is a cross-sectional observation, NOT proof of an activity surge
    versus a historical baseline. Age is pair age, not necessarily token age.
    """
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    old_pairs = 0
    active = []
    for pair in pairs.values():
        created = number(pair.get("pairCreatedAt"))
        if created is None or created <= 0 or created > now_ms:
            continue
        age_days = (now_ms - created) / 86400000
        if age_days < min_age_days:
            continue
        old_pairs += 1
        tx = (pair.get("txns") or {}).get("m5") or {}
        buys, sells = number(tx.get("buys")), number(tx.get("sells"))
        liquidity = number((pair.get("liquidity") or {}).get("usd"))
        volume = number((pair.get("volume") or {}).get("m5"))
        change = number((pair.get("priceChange") or {}).get("h1"))
        if any(x is None or x < 0 for x in (buys, sells, liquidity, volume)):
            continue
        trades = buys + sells
        if liquidity < 20000 or volume < 5000 or trades < 40:
            continue
        ratio = buys / trades if trades else 0
        if ratio < .55:
            continue
        base = pair.get("baseToken") or {}
        active.append({
            "chain": pair.get("chainId"),
            "address": base.get("address"),
            "pair": pair.get("pairAddress"),
            "symbol": base.get("symbol"),
            "pair_age_days": round(age_days, 1),
            "liquidity_usd": round(liquidity),
            "volume_5m_usd": round(volume),
            "trades_5m": int(trades),
            "buy_ratio_5m_pct": round(100 * ratio, 1),
            "change_1h_pct": round(change, 1) if change is not None else None,
            "late_entry_blocked": change is None or change > 150,
            "historical_baseline_verified": False,
            "status": "RESEARCH_ONLY",
        })
    active.sort(key=lambda x: (x["volume_5m_usd"], x["trades_5m"]), reverse=True)
    return {
        "older_pairs_seen": old_pairs,
        "active_older_pairs": len(active),
        "late_entry_blocked": sum(x["late_entry_blocked"] for x in active),
        "examples": active[:limit],
        "paper_entries_triggered": 0,
        "scope": "pre-filter snapshots only; not evidence of a historical reactivation or executable entry",
    }

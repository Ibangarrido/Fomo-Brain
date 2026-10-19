"""V13 prospective meme radar. Discovery is never an authorization to trade."""
import json
import math
from datetime import datetime, timezone

VERSION = "v13-hunter-r1"
MAX_EXPOSURE_EUR = 10.0


def finite(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def observe(pair, now=None):
    """Evaluate one provider snapshot, without inventing holders or wallet activity."""
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware clock required")
    base = pair.get("baseToken") or {}
    chain, address, pool = pair.get("chainId"), base.get("address"), pair.get("pairAddress")
    if not all(isinstance(v, str) and v for v in (chain, address, pool)):
        return None
    liquidity = finite((pair.get("liquidity") or {}).get("usd"))
    cap = finite(pair.get("marketCap") or pair.get("fdv"))
    volume = finite((pair.get("volume") or {}).get("m5"))
    changes = pair.get("priceChange") or {}
    ch5, ch1h = finite(changes.get("m5")), finite(changes.get("h1"))
    tx = (pair.get("txns") or {}).get("m5") or {}
    buys, sells = finite(tx.get("buys")), finite(tx.get("sells"))
    trades = buys + sells if buys is not None and sells is not None else None
    ratio = buys / trades if trades and trades > 0 else None
    created = finite(pair.get("pairCreatedAt"))
    age = (now.timestamp() * 1000 - created) / 60000 if created and created <= now.timestamp() * 1000 else None
    reasons = []
    if liquidity is None or liquidity < 20000:
        reasons.append("LIQUIDITY_UNVERIFIED_OR_LOW")
    if cap is None or not 0 < cap <= 2000000:
        reasons.append("CAP_UNVERIFIED_OR_HIGH")
    if trades is None or trades < 40:
        reasons.append("ACTIVITY_UNVERIFIED_OR_LOW")
    if ratio is None or ratio < .60:
        reasons.append("BUY_PRESSURE_UNVERIFIED_OR_LOW")
    if ch5 is None or not 2 <= ch5 <= 60:
        reasons.append("MOMENTUM_OUT_OF_RANGE")
    if ch1h is None or ch1h > 150:
        reasons.append("LATE_OR_UNKNOWN_1H")
    if age is None or not 2 <= age <= 60:
        reasons.append("PAIR_AGE_OUT_OF_RANGE")
    # No holder, concentration, sell-route, or source trade-age verification in this snapshot.
    return {
        "version": VERSION, "chain": chain, "address": address, "pair": pool,
        "symbol": base.get("symbol"), "received_at": now.isoformat(),
        "price_usd": finite(pair.get("priceUsd")), "liquidity_usd": liquidity,
        "market_cap_usd": cap, "volume_5m_usd": volume,
        "change_5m_pct": ch5, "change_1h_pct": ch1h,
        "trades_5m": trades, "buy_ratio_5m": ratio, "pair_age_minutes": age,
        "discovery_alert": bool(trades is not None and trades >= 10 and
                                ch5 is not None and ch5 > 0),
        "market_gates_pass": not reasons, "blockers": reasons,
        "signal": "VIGILAR" if not reasons else "DESCARTAR_ENTRADA",
        "entry_authorized": False, "execution_verified": False,
        "unknowns": ["holders", "top10_concentration", "sell_route",
                     "provider_market_age", "trader_wallets"],
        "max_exposure_eur": MAX_EXPOSURE_EUR,
    }


def scan(pairs, now=None):
    """Keep observations even when a market gate rejects a prospective trade."""
    rows = [observe(pair, now) for pair in pairs]
    return [row for row in rows if row is not None]


def report(pairs, now=None):
    rows = scan(pairs, now)
    return {"version": VERSION, "paper_only": True, "entries": 0,
            "observed": len(rows), "discovery_alerts": sum(r["discovery_alert"] for r in rows),
            "market_gate_passes": sum(r["market_gates_pass"] for r in rows),
            "signals": rows}

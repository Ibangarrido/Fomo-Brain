"""V13 prospective meme radar. Discovery is never an authorization to trade."""
import json
import math
from datetime import datetime, timezone

VERSION = "v13-hunter-r5-age-segmented-research"
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
    ch6, ch24 = finite(changes.get("h6")), finite(changes.get("h24"))
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
        "change_6h_pct": ch6, "change_24h_pct": ch24,
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


def trend_observation(row, previous=()):
    """Research-only 4h observation from timestamped snapshots; never fake OHLC candles.

    6h provider change is a *proxy*, not a 4h candle. A 4h direction can only
    be calculated once >=4 hours of distinct valid historical observations exist.
    """
    from datetime import datetime, timedelta
    result = dict(row)
    now = datetime.fromisoformat(row["received_at"])
    mint, chain = row["address"], row["chain"]
    samples = []
    for item in previous:
        if item.get("address") != mint or item.get("chain") != chain:
            continue
        try:
            t = datetime.fromisoformat(item["received_at"])
            p = finite(item.get("price_usd"))
            if p is not None and p > 0 and now-timedelta(hours=6) <= t < now:
                samples.append((t, p))
        except (KeyError, TypeError, ValueError):
            continue
    samples.sort(key=lambda x: x[0])
    price = finite(row.get("price_usd"))
    baseline = [(t, p) for t, p in samples if now-timedelta(hours=5) <= t <= now-timedelta(hours=4)]
    change4h = (price / baseline[-1][1] - 1) * 100 if baseline and price is not None and price > 0 else None
    # 15m and 5m confirmations require actual observations, not 6h proxies.
    recent15 = [(t,p) for t,p in samples if now-timedelta(minutes=20) <= t <= now-timedelta(minutes=10)]
    change15 = (price/recent15[-1][1]-1)*100 if recent15 and price is not None and price > 0 else None
    rising4h = change4h is not None and change4h > 0
    confirming15 = change15 is not None and change15 > 0
    confirming5 = row.get("change_5m_pct") is not None and 0 < row["change_5m_pct"] <= 25
    result["strategy"] = "TENDENCIA_4H_ENTRADA_5M"
    result["trend_4h_pct_observed"] = round(change4h, 4) if change4h is not None else None
    result["confirmation_15m_pct_observed"] = round(change15, 4) if change15 is not None else None
    result["trend_6h_pct_provider_proxy"] = row.get("change_6h_pct")
    result["trend_data_sufficient"] = change4h is not None and change15 is not None
    result["trend_watch"] = bool(rising4h and confirming15 and confirming5)
    result["trend_signal"] = ("VIGILAR_TENDENCIA" if result["trend_watch"] else
                              "HISTORIAL_INSUFICIENTE" if not result["trend_data_sufficient"] else
                              "SIN_CONFIRMACION")
    result["trend_entry_authorized"] = False
    return result


def continuation_observation(row, previous=()):
    """Paper-only continuation watch; uses strictly earlier observed snapshots.

    An alert is not a verified entry. 55% buy ratio is only a research gate;
    it never relaxes the legacy 60% market gate or liquidity safety check.
    """
    from datetime import datetime, timedelta
    result = dict(row)
    now = datetime.fromisoformat(row["received_at"])
    samples = []
    for item in previous:
        if item.get("chain") != row.get("chain") or item.get("address") != row.get("address"):
            continue
        try:
            t = datetime.fromisoformat(item["received_at"])
            p = finite(item.get("price_usd"))
            v = finite(item.get("volume_5m_usd"))
            if now-timedelta(minutes=90) <= t < now and p is not None and p > 0:
                samples.append((t, p, v))
        except (KeyError, TypeError, ValueError):
            continue
    samples.sort(key=lambda item: item[0])
    price = finite(row.get("price_usd"))
    liquidity = finite(row.get("liquidity_usd"))
    ratio = finite(row.get("buy_ratio_5m"))
    trades = finite(row.get("trades_5m"))
    momentum = finite(row.get("change_5m_pct"))
    volume = finite(row.get("volume_5m_usd"))
    prior_prices = [p for _,p,_ in samples]
    prior_volumes = [v for _,_,v in samples if v is not None and v > 0]
    prior_high = max(prior_prices) if len(prior_prices) >= 2 else None
    # Relative volume is meaningful only against observed prior samples.
    volume_baseline = sum(prior_volumes)/len(prior_volumes) if len(prior_volumes) >= 2 else None
    relative_volume = volume/volume_baseline if volume_baseline and volume is not None else None
    breakout = price is not None and prior_high is not None and price > prior_high * 1.01
    active = trades is not None and trades >= 40 and ratio is not None and ratio >= .55
    liquid = liquidity is not None and liquidity >= 20000
    # No late-pump paper entry; high momentum is observed but not recommended.
    not_extended = momentum is not None and 0 < momentum <= 60
    result["continuation_strategy"] = "RUPTURA_CONTINUACION_5_15M"
    result["continuation_prior_high_usd"] = prior_high
    result["continuation_relative_volume"] = round(relative_volume, 3) if relative_volume is not None else None
    result["continuation_buy_pressure_research"] = bool(active)
    result["continuation_data_sufficient"] = prior_high is not None and volume_baseline is not None
    result["continuation_watch"] = bool(breakout and active and liquid and not_extended and
                                         relative_volume is not None and relative_volume >= 1.2)
    result["continuation_signal"] = ("VIGILAR_RUPTURA" if result["continuation_watch"] else
                                      "HISTORIAL_INSUFICIENTE" if not result["continuation_data_sufficient"] else
                                      "SIN_CONFIRMACION")
    result["continuation_entry_authorized"] = False
    return result


def mature_continuation_observation(row, previous=()):
    """1–6h follow-through watch, NOT an entry signal; independent of launch age gate.

    Use previous sampled prices only. A pump already above +150% in 1h is
    observed for research but cannot produce a qualified mature watch.
    """
    from datetime import datetime, timedelta
    result = dict(row)
    now = datetime.fromisoformat(row["received_at"])
    age = finite(row.get("pair_age_minutes"))
    price = finite(row.get("price_usd"))
    cap = finite(row.get("market_cap_usd"))
    liquidity = finite(row.get("liquidity_usd"))
    trades = finite(row.get("trades_5m"))
    ratio = finite(row.get("buy_ratio_5m"))
    change5 = finite(row.get("change_5m_pct"))
    change1h = finite(row.get("change_1h_pct"))
    samples = []
    for item in previous:
        if item.get("chain") != row.get("chain") or item.get("address") != row.get("address"):
            continue
        try:
            t = datetime.fromisoformat(item["received_at"])
            p = finite(item.get("price_usd"))
            if now-timedelta(minutes=75) <= t <= now-timedelta(minutes=10) and p is not None and p > 0:
                samples.append((t, p))
        except (KeyError, TypeError, ValueError):
            continue
    samples.sort()
    prior_high = max((p for _, p in samples), default=None)
    # At least two separate observations and >=10m time coverage are required.
    enough = len(samples) >= 2 and (samples[-1][0]-samples[0][0]).total_seconds() >= 600
    breakout = bool(enough and price is not None and price > prior_high*1.01)
    age_ok = age is not None and 60 < age <= 360
    safety = (cap is not None and 0 < cap <= 2000000 and
              liquidity is not None and liquidity >= 20000 and
              trades is not None and trades >= 40 and
              ratio is not None and ratio >= .60 and
              change5 is not None and 0 < change5 <= 25 and
              change1h is not None and change1h <= 150)
    result["mature_strategy"] = "CONTINUACION_1_6H"
    result["mature_data_sufficient"] = enough
    result["mature_prior_high_usd"] = prior_high
    result["mature_watch"] = bool(age_ok and breakout and safety)
    result["mature_signal"] = ("VIGILAR_CONTINUACION_1_6H" if result["mature_watch"] else
                               "HISTORIAL_INSUFICIENTE" if not enough else
                               "SIN_CONFIRMACION")
    result["mature_entry_authorized"] = False
    return result

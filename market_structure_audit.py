"""Research-only market structure report from recorded pair snapshots.

No wallet attribution is possible from aggregated buys/sells. This module
never authorizes trades, changes portfolio state, or invents whale flow.
"""
from collections import Counter
from datetime import datetime, timezone
import json


def report(tokens, cutoff=None):
    cutoff = cutoff or datetime.now(timezone.utc)
    counts = Counter()
    examples = []
    for row in tokens.values():
        if row.get("cohort") == "manual_after_event":
            counts["retrospective_excluded"] += 1
            continue
        first = row.get("first_rejection") or row.get("first") or {}
        last = row.get("last") or {}
        if not first.get("pair") or not last or first.get("pair") != last.get("pair"):
            counts["missing_or_changed_pair"] += 1
            continue
        try:
            first_time = datetime.fromisoformat(first["received_at"])
            last_time = datetime.fromisoformat(last["received_at"])
            if first_time.tzinfo is None or last_time.tzinfo is None or last_time > cutoff or last_time <= first_time:
                raise ValueError("bad receipt interval")
        except (ValueError, KeyError, TypeError):
            counts["invalid_time"] += 1
            continue
        if (last_time-first_time).total_seconds() > 3600:
            counts["outside_one_hour"] += 1
            continue
        try:
            p0, p1 = float(first["price"]), float(last["price"])
            l0, l1 = float(first["liquidity"]), float(last["liquidity"])
            ratio = float(last["buy_ratio5m"])
            if min(p0, p1, l0, l1) <= 0 or not 0 <= ratio <= 1:
                raise ValueError("invalid market values")
        except (ValueError, TypeError, KeyError):
            counts["missing_market_fields"] += 1
            continue
        change = 100*(p1/p0-1)
        liquidity_change = 100*(l1/l0-1)
        if change >= 20 and liquidity_change >= 0 and ratio >= .6:
            label = "PRICE_UP_WITH_LIQUIDITY_AND_BUY_COUNT"
        elif change <= -20 and liquidity_change <= -5:
            label = "PRICE_DROP_AND_LIQUIDITY_CONTRACTION"
        else:
            label = "UNCLASSIFIED"
        counts[label] += 1
        if len(examples) < 10:
            examples.append({"symbol": row.get("symbol"), "pair": first["pair"],
                             "label": label, "price_change_pct": round(change, 2),
                             "liquidity_change_pct": round(liquidity_change, 2),
                             "buy_count_ratio": round(ratio, 3)})
    return {"version": "market-structure-observation-r1", "counts": dict(counts),
            "examples": examples, "whale_buy_sell_usd": None,
            "whale_wallets_verified": False, "independent_wallets_verified": False,
            "entry_authorized": False,
            "scope": "two sampled same-pair receipts within one hour; rolling 5m buy transaction count, NOT dollar net flow, candles, or whale evidence"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_json")
    args = parser.parse_args()
    with open(args.audit_json, encoding="utf-8") as handle:
        state = json.load(handle)
    print(json.dumps(report(state["tokens"]), ensure_ascii=False))

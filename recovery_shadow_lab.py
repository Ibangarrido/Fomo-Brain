"""Read-only PAPER shadow evaluator for 50%-60% buy-pressure recoveries.

Input: JSON list of observations with token, timestamp, buy_ratio, price,
liquidity, volume_5m, and optionally eligible (boolean).
No broker calls, wallet operations, or live trading.
"""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone


def evaluate(rows, horizons=(5, 15), tolerance_seconds=120):
    by_token = defaultdict(list)
    for row in rows:
        if not all(k in row for k in ("token", "timestamp", "buy_ratio", "price")):
            continue
        if not (0.50 <= float(row["buy_ratio"]) < 0.60):
            continue
        if float(row["price"]) <= 0:
            continue
        if row.get("eligible") is not True:
            continue
        by_token[str(row["token"])].append(row)
    all_prices = defaultdict(list)
    for row in rows:
        if all(k in row for k in ("token", "timestamp", "price")) and float(row["price"]) > 0:
            all_prices[str(row["token"])].append(row)
    for token in all_prices:
        all_prices[token].sort(key=lambda r: r["timestamp"])
    out = []
    for token, entries in by_token.items():
        for entry in entries:
            for minutes in horizons:
                target = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).timestamp() + 60 * minutes
                matches = []
                for future in all_prices[token]:
                    t = datetime.fromisoformat(future["timestamp"].replace("Z", "+00:00")).timestamp()
                    if t > datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).timestamp() and abs(t-target) <= tolerance_seconds:
                        matches.append((abs(t-target), future))
                future = min(matches, key=lambda x:x[0])[1] if matches else None
                out.append({"token": token, "entry_timestamp": entry["timestamp"], "horizon_min": minutes,
                            "return_pct": round((float(future["price"])/float(entry["price"])-1)*100, 4) if future else None,
                            "status": "observed" if future else "missing_checkpoint"})
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="JSON array of timestamped observations")
    parser.add_argument("--output", default="recovery_shadow_report.json")
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as f:
        rows = json.load(f)
    report = evaluate(rows)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "paper_only": True,
                   "note": "Gross hypothetical returns; excludes fees, slippage, liquidity impact and execution.",
                   "results": report}, f, indent=2)
    print(f"Evaluated {len(report)} shadow checkpoints; no trading actions.")

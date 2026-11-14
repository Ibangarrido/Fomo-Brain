"""Offline, read-only learning report for rejected PAPER candidates.

Input JSONL rows: token, rejected_at, reason, price_at_rejection, and
observations [{minutes_after, price, liquidity_usd, buy_ratio}].
Never opens orders or modifies trading thresholds.
"""
import argparse
import json
import math
from collections import defaultdict


def finite_positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def evaluate(rows, horizons=(5, 15, 60), tolerance_minutes=2):
    by_reason = defaultdict(lambda: {"samples": 0, "eligible": 0, "horizons": defaultdict(list)})
    for row in rows:
        reason = row.get("reason") or "UNKNOWN"
        stats = by_reason[reason]
        stats["samples"] += 1
        start = row.get("price_at_rejection")
        if not finite_positive(start):
            continue
        stats["eligible"] += 1
        for horizon in horizons:
            choices = [obs for obs in row.get("observations", [])
                       if finite_positive(obs.get("price"))
                       and isinstance(obs.get("minutes_after"), (int, float))
                       and abs(obs["minutes_after"] - horizon) <= tolerance_minutes]
            if not choices:
                continue
            observation = min(choices, key=lambda obs: abs(obs["minutes_after"] - horizon))
            stats["horizons"][horizon].append(100 * (observation["price"] / start - 1))
    output = {}
    for reason, stats in sorted(by_reason.items()):
        results = {}
        for horizon in horizons:
            returns = sorted(stats["horizons"][horizon])
            n = len(returns)
            results[str(horizon)] = {
                "observed": n, "missing": stats["eligible"] - n,
                "median_gross_pct": returns[n // 2] if n % 2 else (returns[n // 2 - 1] + returns[n // 2]) / 2 if n else None,
                "positive_count": sum(x > 0 for x in returns),
                "negative_count": sum(x < 0 for x in returns),
            }
        output[reason] = {"samples": stats["samples"], "eligible": stats["eligible"], "horizons": results}
    return {"version": "rejection-learning-shadow-r1", "by_reason": output,
            "warning": "Observed gross changes are not executable returns. Missing future observations are reported; no rule is automatically promoted."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", help="Historical rejection observations, one JSON object per line")
    args = parser.parse_args()
    with open(args.jsonl, encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    print(json.dumps(evaluate(rows), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

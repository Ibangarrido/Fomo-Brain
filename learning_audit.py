"""Research-only learning report from prospective, same-pair checkpoints.

No model updates, orders, or portfolio mutations. Do not treat sampled price
changes as executable P&L or as verified candle highs.
"""
import json
from collections import defaultdict
from datetime import datetime, timedelta


def summarize(tokens, cutoff, minimum=20):
    """Only evaluate checkpoints matured by cutoff; exclude manual hindsight."""
    buckets = defaultdict(lambda: {"eligible": 0, "up20": 0, "down20": 0})
    skipped = defaultdict(int)
    for row in tokens.values():
        if row.get("cohort") == "manual_after_event":
            skipped["retrospective"] += 1
            continue
        baseline = row.get("first_rejection")
        if not baseline or not baseline.get("pair"):
            skipped["no_prospective_pair"] += 1
            continue
        try:
            at = datetime.fromisoformat(baseline["received_at"])
            if at.tzinfo is None or cutoff.tzinfo is None:
                raise ValueError("timezone required")
        except (ValueError, TypeError, KeyError):
            skipped["bad_time"] += 1
            continue
        # All groups are defined at the rejection timestamp, not by future highs.
        reasons = baseline.get("entry_rejections") or {}
        group = "buy_ratio" if isinstance(reasons, dict) and any(
            "ratio compras" in str(reason).lower() or "buy_ratio" in str(reason).lower()
            for reason in reasons.values()) else "other"
        checkpoint = row.get("post_rejection_checkpoints", {}).get("30m")
        if at + timedelta(minutes=30) > cutoff:
            skipped["not_mature"] += 1
        elif not checkpoint or checkpoint.get("lag_seconds") is None or not 0 <= checkpoint["lag_seconds"] <= 120:
            skipped["missing_or_late"] += 1
        elif checkpoint.get("pair_changed") is not False:
            skipped["changed_or_unknown_pair"] += 1
        else:
            buckets[group]["eligible"] += 1
            buckets[group]["up20"] += int(checkpoint.get("sampled_up_20pct") is True)
            buckets[group]["down20"] += int(checkpoint.get("sampled_down_20pct") is True)
    report = {k: {**v, "up20_rate": round(v["up20"]/v["eligible"], 3)}
              for k, v in buckets.items()}
    return {"status": "EVIDENCE_ONLY" if sum(v["eligible"] for v in report.values()) >= minimum else "INSUFFICIENT_DATA",
            "minimum": minimum, "groups": report, "excluded": dict(skipped),
            "scope": "prospective same-pair timely 30m sampled observations; not trading P&L; no policy changes"}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("audit_json")
    p.add_argument("--cutoff", required=True, help="ISO timestamp with UTC offset")
    args = p.parse_args()
    with open(args.audit_json, encoding="utf-8") as handle:
        state = json.load(handle)
    print(json.dumps(summarize(state["tokens"], datetime.fromisoformat(args.cutoff)), indent=2))

"""Research-only report: quantify rejected-token second looks without trading."""
import json
import os
from memecoin_trap_research import assess

SOURCE = "fomo_opportunity_audit_r1.json"
OUTPUT = "fomo_learning_report_r1.json"


def summarize(state):
    rows = [r for r in state.get("tokens", {}).values()
            if r.get("cohort") == "automatic_prospective"
            and (r.get("first") or {}).get("entry_rejections")]
    requalified = []
    first_blockers = {}
    requalified_within_15m = 0
    missing_second_look = 0
    trap_flags = {}
    trap_evaluable = 0
    for row in rows:
        first = row.get("first") or {}
        for rejection in first.get("entry_rejections") or []:
            reason = str(rejection).split(" | ", 1)[-1][:120]
            first_blockers[reason] = first_blockers.get(reason, 0) + 1
        history = row.get("second_look_history") or []
        # Only evaluate a raw pair snapshot when it exists; do not invent market data.
        raw_pair = row.get("last_raw_pair")
        if isinstance(raw_pair, dict):
            trap_evaluable += 1
            for flag in assess(raw_pair)["risk_flags"]:
                trap_flags[flag] = trap_flags.get(flag, 0) + 1
        matching = [h for h in history if h.get("market_gates_pass") is True
                    and h.get("checks", {}).get("same_pair_as_rejection") is True]
        if not history:
            missing_second_look += 1
        if matching:
            requalified.append(row)
            if any(isinstance(h.get("minutes_since_rejection"), (int, float))
                   and 0 <= h["minutes_since_rejection"] <= 15 for h in matching):
                requalified_within_15m += 1
    return {
        "version": "trading-learning-report-r1",
        "mode": "research_only",
        "rejected_automatic_observed": len(rows),
        "requalified_market_only_same_pair": len(requalified),
        "requalified_within_15m_same_pair": requalified_within_15m,
        "missing_second_look": missing_second_look,
        "trap_snapshots_evaluable": trap_evaluable,
        "trap_flag_counts": trap_flags,
        "rejection_reason_occurrences": dict(sorted(first_blockers.items(), key=lambda kv: (-kv[1], kv[0]))[:15]),
        "unverified_full_eligibility": True,
        "real_orders": 0,
        "limitations": "Market screens are not executable fills, profits, candle confirmation or wallet eligibility. No future data used to authorize an entry.",
    }


def main():
    if not os.path.isfile(SOURCE):
        print("LEARNING REPORT: audit source absent; no invented results")
        return
    with open(SOURCE, encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("version") != 1 or not isinstance(state.get("tokens"), dict):
        raise ValueError("Incompatible opportunity audit")
    report = summarize(state)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    print("LEARNING REPORT " + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()

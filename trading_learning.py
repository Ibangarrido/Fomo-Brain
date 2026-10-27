"""Research-only report: quantify rejected-token second looks without trading."""
import json
import os

SOURCE = "fomo_opportunity_audit_r1.json"
OUTPUT = "fomo_learning_report_r1.json"


def summarize(state):
    rows = [r for r in state.get("tokens", {}).values()
            if r.get("cohort") == "automatic_prospective"
            and (r.get("first") or {}).get("entry_rejections")]
    requalified = []
    for row in rows:
        first = row.get("first") or {}
        history = row.get("second_look_history") or []
        matching = [h for h in history if h.get("market_gates_pass") is True
                    and h.get("checks", {}).get("same_pair_as_rejection") is True]
        if matching:
            requalified.append(row)
    return {
        "version": "trading-learning-report-r1",
        "mode": "research_only",
        "rejected_automatic_observed": len(rows),
        "requalified_market_only_same_pair": len(requalified),
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

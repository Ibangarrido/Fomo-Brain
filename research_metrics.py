"""Read-only paper research diagnostics; never selects a winner or writes wallets."""
import argparse
import json
import math
from datetime import datetime


def instant(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("Research timestamps require a timezone")
    return result


def identity(row):
    key = tuple(row.get(k) for k in ("chain", "address", "opened_at"))
    if not all(isinstance(v, str) and v for v in key):
        raise ValueError("Incomplete position identity")
    instant(key[2])
    return key


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def wallet_report(state, baseline_key):
    baseline = state[baseline_key]
    start = instant(baseline["at"])
    observations = state.get("observations", [])
    obs = observations[-1] if observations else {}
    as_of = instant(obs["at"]) if obs.get("at") else None
    if as_of is not None and as_of < start:
        raise ValueError("Observation predates experiment baseline")
    groups = {}
    active = {identity(p) for p in state.get("positions", [])}
    for leg in state.get("closed", []):
        key = identity(leg)
        profit = leg.get("profit")
        if not finite(profit) or not isinstance(leg.get("exit_reason"), str):
            raise ValueError("Invalid sale leg")
        closed = instant(leg["closed_at"])
        if closed < instant(key[2]):
            raise ValueError("Sale predates entry")
        if as_of is not None and closed > as_of:
            raise ValueError("Sale postdates observation")
        group = groups.setdefault(key, {"profit": 0.0, "completed_at": None, "policies": set()})
        group["profit"] += profit
        if leg["exit_reason"] != "PARCIAL +30%":
            previous = group["completed_at"]
            group["completed_at"] = max(previous, closed) if previous else closed
        group["policies"].add((leg.get("entry_policy_version") or "UNKNOWN",
                               leg.get("entry_risk_policy_version") or "UNKNOWN"))
    new, inherited, policies = [], [], set()
    partial_only = 0
    for key, group in groups.items():
        completed = group["completed_at"]
        if key in active or completed is None:
            partial_only += 1
            continue
        if completed < start:
            continue
        if instant(key[2]) < start:
            inherited.append(group["profit"])
        else:
            new.append(group["profit"])
            policies.update(group["policies"])
    unknown = sum(p.get("quote_status") != "OK" for p in state.get("positions", []))
    complete = (as_of is not None and obs.get("valuation_complete") is True and unknown == 0
                and obs.get("unverified_quotes") == 0 and finite(obs.get("estimated_equity")))
    equity = obs.get("estimated_equity") if complete else None
    base_equity = baseline.get("equity", baseline.get("total_equity"))
    delta = equity - base_equity if complete and finite(base_equity) else None
    return {
        "version": "research-metrics-r1", "baseline_at": baseline["at"],
        "as_of": obs.get("at"), "model_currency": "EUR with fixed USD/EUR=1",
        "valuation_complete": complete, "equity_delta": delta,
        "open_positions": len(active), "unverified_open_positions": unknown,
        "sale_legs_all_history": len(state.get("closed", [])),
        "new_completed_positions": len(new), "new_winners": sum(p > 0 for p in new),
        "new_losers": sum(p < 0 for p in new), "new_flat": sum(p == 0 for p in new),
        "new_completed_realized_profit": sum(new),
        "inherited_completed_positions": len(inherited),
        "inherited_lifetime_realized_profit": sum(inherited),
        "positions_with_sales_still_open_or_partial_only": partial_only,
        "new_completed_entry_and_risk_policies": [list(p) for p in sorted(policies)],
        "mixed_or_unknown_policies": len(policies) > 1 or any("UNKNOWN" in p for p in policies),
        "profitability_demonstrated": False, "execution_verified": False,
    }


def compare(control, variant, baseline_key):
    if control[baseline_key] != variant[baseline_key]:
        raise ValueError("Different experiment baselines")
    c, v = wallet_report(control, baseline_key), wallet_report(variant, baseline_key)
    times = [instant(row["as_of"]) if row["as_of"] else None for row in (c, v)]
    gap = abs((times[1] - times[0]).total_seconds()) if all(times) else None
    advantage = (v["equity_delta"] - c["equity_delta"]
                 if c["equity_delta"] is not None and v["equity_delta"] is not None else None)
    return {"control": c, "variant": v, "relative_equity_advantage": advantage,
            "snapshot_gap_seconds": gap, "simultaneous_quotes_verified": False,
            "statistical_significance": None, "winner_selected": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control")
    parser.add_argument("variant")
    parser.add_argument("--baseline", required=True)
    args = parser.parse_args()
    with open(args.control) as handle:
        control = json.load(handle)
    with open(args.variant) as handle:
        variant = json.load(handle)
    print(json.dumps(compare(control, variant, args.baseline), indent=2, allow_nan=False))

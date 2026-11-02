"""Fail-closed validation of the main Clean V1 ledger for isolated PR shadow runs.

Never creates a wallet; never touches the production artifact. The PR job
restores the main artifact into an ephemeral runner and uploads a distinct name.
"""
import json
import math
import os
import sys
from pathlib import Path

STATE = Path("brain_clean_v1_state.json")
BASELINE = Path("brain_clean_v1_shadow_baseline.json")
COMPARISON = Path("brain_clean_v1_shadow_comparison.json")


def validate(state):
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ValueError("Missing or incompatible Clean V1 ledger; refusing shadow bootstrap")
    cash = state.get("cash")
    if isinstance(cash, bool) or not isinstance(cash, (int, float)) or not math.isfinite(cash) or cash < 0:
        raise ValueError("Invalid PAPER cash; refusing shadow run")
    if not isinstance(state.get("positions"), dict) or not isinstance(state.get("closed"), list):
        raise ValueError("Incomplete PAPER holdings/closed trades; refusing shadow run")
    if not isinstance(state.get("history"), dict):
        raise ValueError("Missing PAPER history; refusing shadow run")
    prior = state.get("last_run")
    if not isinstance(prior, dict) or not prior.get("id") or not prior.get("completed_at"):
        raise ValueError("Missing real previous run provenance; refusing silent 100 EUR reset")
    return {"cash_eur": cash, "open_positions": len(state["positions"]),
            "closed_trades": len(state["closed"]), "previous_run": prior}


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def preflight():
    if not STATE.is_file():
        raise ValueError("Production Clean V1 artifact not restored; refusing shadow bootstrap")
    baseline = validate(read_json(STATE))
    BASELINE.write_text(json.dumps(baseline, indent=2, sort_keys=True), encoding="utf-8")
    print("CLEAN_SHADOW_BASELINE " + json.dumps(baseline, sort_keys=True))


def finalize():
    baseline = read_json(BASELINE)
    state = read_json(STATE)
    report = read_json("brain_clean_v1_report.json")
    current = state.get("last_run") or {}
    expected = os.environ.get("CLEAN_SHADOW_HEAD_SHA")
    if not expected or current.get("sha") != expected or report.get("run", {}).get("sha") != expected:
        raise ValueError("Shadow provenance mismatch: wrong code revision")
    if report.get("previous_run", {}).get("id") != baseline["previous_run"]["id"]:
        raise ValueError("Shadow restored the wrong baseline")
    result = {"source": "PR shadow clone of main PAPER ledger, NOT main state",
              "branch_head_sha": expected, "baseline": baseline,
              "shadow_cash_eur": state["cash"], "shadow_open_positions": len(state["positions"]),
              "shadow_closed_trades": len(state["closed"]), "shadow_report": report}
    COMPARISON.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print("CLEAN_SHADOW_COMPARISON " + json.dumps({
        "baseline_cash_eur": baseline["cash_eur"], "shadow_cash_eur": state["cash"],
        "baseline_closed": baseline["closed_trades"], "shadow_closed": len(state["closed"]),
        "sha": expected}, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "finalize"):
        raise SystemExit("Usage: clean_v1_shadow.py preflight|finalize")
    (preflight if sys.argv[1] == "preflight" else finalize)()

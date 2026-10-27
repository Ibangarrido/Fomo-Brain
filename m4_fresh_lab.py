"""Independent, opt-in M4 PAPER experiment. Never imports or transfers legacy balances."""
import json
import os

FILE = "fomo_lab_m4_fresh_r1.json"

def run(ranking, simulate):
    if os.getenv("BRAIN_M4_FRESH_LAB", "0") != "1":
        return
    # The core simulator initializes a missing file with 100 EUR PAPER,
    # and reuses it on later cycles. Historical M4 files remain untouched.
    simulate(ranking, FILE, "M4 FRESH PAPER r1", confirm=True,
             entry_mode="early", min_buy_ratio=0.60)
    with open(FILE, encoding="utf-8") as handle:
        state = json.load(handle)
    print("M4 FRESH STATUS " + json.dumps({
        "file": FILE, "paper_only": True,
        "cash": state["cash"], "reserve": state["reserve"],
        "open": len(state["positions"]), "closed": len(state["closed"]),
        "unknown_quotes": sum(p.get("quote_status") != "OK" for p in state["positions"]),
    }, ensure_ascii=False))

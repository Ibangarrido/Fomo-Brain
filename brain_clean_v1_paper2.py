"""Independent PAPER portfolio 2. Never imports or mutates CONTROL ledger.

This module intentionally has no automatic bootstrap on repeated runs.
The baseline is a committed immutable seed, not a replacement for existing state.
"""
import copy
import json
import math
from pathlib import Path
import brain_clean_v1 as brain

PORTFOLIO_ID = "clean-v1-paper-2"
SEED_FILE = "brain_clean_v1_paper2_seed.json"
STATE_FILE = "brain_clean_v1_paper2_state.json"

def seed():
    state = brain.new_state()
    state["portfolio_id"] = PORTFOLIO_ID
    state["experiment"] = "independent PAPER 100 EUR; original CONTROL unchanged"
    return state

def assert_never_bootstrapped(artifact_listing):
    """Fail closed even when the previous PAPER2 artifact has expired."""
    if not isinstance(artifact_listing, dict):
        raise ValueError("Invalid PAPER2 artifact response")
    count = artifact_listing.get("total_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("Unknown PAPER2 artifact history: refusing bootstrap")
    if count:
        raise FileExistsError("PAPER2 artifact history exists, including expired: never reset")
    if artifact_listing.get("artifacts") != []:
        raise ValueError("Inconsistent PAPER2 artifact response: refusing bootstrap")


def initialize_once(path=STATE_FILE):
    """Explicit one-time local PAPER bootstrap; never overwrite an existing ledger."""
    target = Path(path)
    state = seed()
    # Exclusive creation is atomic: existing state is never reset.
    with target.open("x", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, sort_keys=True, indent=2)
    return state


def load_existing(path=STATE_FILE):
    """Fail closed: no silent reset of portfolio 2 after its first run."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError("PAPER2 state missing; restore dedicated artifact, never reset")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("portfolio_id") != PORTFOLIO_ID or state.get("version") != 1:
        raise ValueError("Wrong PAPER2 ledger: refusing cross-portfolio import")
    cash = state.get("cash")
    if isinstance(cash, bool) or not isinstance(cash, (int, float)) or not math.isfinite(cash) or cash < 0:
        raise ValueError("Invalid PAPER2 cash: refusing corrupted ledger")
    if not isinstance(state.get("positions"), dict) or not isinstance(state.get("closed"), list):
        raise ValueError("Invalid PAPER2 positions/history: refusing corrupted ledger")
    if any(not isinstance(pos, dict) for pos in state["positions"].values()):
        raise ValueError("Invalid PAPER2 position record: refusing corrupted ledger")
    if any(not isinstance(trade, dict) for trade in state["closed"]):
        raise ValueError("Invalid PAPER2 closed trade: refusing corrupted ledger")
    return state

def observe(state, samples, now=None):
    if state.get("portfolio_id") != PORTFOLIO_ID:
        raise ValueError("Not a PAPER2 ledger")
    # CONTROL logic reused unchanged, with an independent in-memory ledger.
    return brain.step(state, samples, now)

def baseline_report():
    """Baseline only; no market data, trades, or exits are implied."""
    state = seed()
    return {"portfolio_id": PORTFOLIO_ID, "cash_eur": state["cash"],
            "positions_open": 0, "closed_trades": 0,
            "realized_pnl_eur": 0.0, "market_data_observed": False,
            "status": "READY_NOT_RUNNING"}

if __name__ == "__main__":
    print(json.dumps(baseline_report(), ensure_ascii=False, sort_keys=True))

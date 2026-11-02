"""Independent PAPER portfolio 2. Never imports or mutates CONTROL ledger.

This module intentionally has no automatic bootstrap on repeated runs.
The baseline is a committed immutable seed, not a replacement for existing state.
"""
import copy
import json
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

def load_existing(path=STATE_FILE):
    """Fail closed: no silent reset of portfolio 2 after its first run."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError("PAPER2 state missing; restore dedicated artifact, never reset")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("portfolio_id") != PORTFOLIO_ID or state.get("version") != 1:
        raise ValueError("Wrong PAPER2 ledger: refusing cross-portfolio import")
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

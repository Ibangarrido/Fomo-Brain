"""Independent whale-following PAPER ledger; not connected to trading APIs.

The portfolio is intentionally dormant until a Surgz wallet is independently
verified. Never reset existing state or mix with CONTROL/PAPER2.
"""
import json
from pathlib import Path

PORTFOLIO_ID = "surgz-whale-shadow-v1"
STATE_FILE = "surgz_whale_paper_state.json"
INITIAL_EUR = 100.0

def seed():
    return {"portfolio_id": PORTFOLIO_ID, "version": 1, "mode": "PAPER_ONLY",
            "cash_eur": INITIAL_EUR, "reserved_eur": 0.0,
            "positions": {}, "closed": [], "observations": [],
            "wallet": None, "wallet_attribution": "UNVERIFIED",
            "status": "WAITING_FOR_VERIFIED_WALLET",
            "realizable_equity_eur": None}

def load_existing(path=STATE_FILE):
    """Fail closed rather than silently resetting missing or corrupt state."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError("Whale PAPER state missing; restore artifact, never reset")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("portfolio_id") != PORTFOLIO_ID or state.get("mode") != "PAPER_ONLY":
        raise ValueError("Wrong portfolio: refusing cross-ledger import")
    if state.get("version") != 1:
        raise ValueError("Unsupported whale ledger version")
    return state

def observe(state, event):
    """Record an observation without executing or pretending to copy a trade."""
    if state.get("portfolio_id") != PORTFOLIO_ID or state.get("mode") != "PAPER_ONLY":
        raise ValueError("Wrong portfolio")
    if not isinstance(event, dict):
        raise ValueError("Invalid observation")
    signature = event.get("signature")
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError("Missing transaction signature")
    if any(x.get("signature") == signature for x in state["observations"]):
        return {"status": "DUPLICATE", "paper_entry": False}
    attributed = state.get("wallet_attribution") == "VERIFIED" and bool(state.get("wallet"))
    record = {"signature": signature, "token": event.get("token"),
              "status": "ATTRIBUTION_VERIFIED_OBSERVATION" if attributed
                        else "UNATTRIBUTED_OBSERVATION",
              "paper_entry": False}
    state["observations"].append(record)
    return record

def report(state):
    if state.get("portfolio_id") != PORTFOLIO_ID:
        raise ValueError("Wrong portfolio")
    return {"portfolio_id": PORTFOLIO_ID, "status": state["status"],
            "cash_eur": state["cash_eur"], "positions_open": len(state["positions"]),
            "closed_trades": len(state["closed"]),
            "observations": len(state["observations"]),
            "wallet_attribution": state["wallet_attribution"],
            "realizable_equity_eur": None, "paper_only": True}

if __name__ == "__main__":
    print(json.dumps(report(seed()), sort_keys=True))

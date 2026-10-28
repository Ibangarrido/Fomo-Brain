"""Create independent PAPER v2 wallets without resetting or selling legacy positions."""
import json
import os
from datetime import datetime, timezone

WALLETS = {
    "m4_fresh": "fomo_lab_m4_fresh_r2.json",
    "continuation_control": "fomo_lab_continuation_control_r2.json",
}

def initialize(name, directory=".", now=None):
    if name not in WALLETS:
        raise ValueError("Unknown PAPER wallet")
    path = os.path.join(directory, WALLETS[name])
    if os.path.lexists(path):
        raise FileExistsError("PAPER wallet already exists; never overwrite or reset")
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    state = {
        "version": 1, "started_at": timestamp, "cash": 100.0, "reserve": 0.0,
        "positions": [], "closed": [], "seen": [], "observations": [],
        "fresh_start": {"version": "paper-r2", "wallet": name,
                        "initial_eur": 100.0,
                        "legacy_wallets_preserved": True,
                        "historical_losses_not_recovered": True,
                        "real_trading": False},
    }
    if name == "continuation_control":
        state["continuation_experiment"] = {"version": "continuation-r1", "arm": "control"}
        state["continuation_baseline"] = {
            "version": "continuation-r1", "at": timestamp,
            "initial_eur": 100.0, "execution_verified": False,
            "scope": "independent new PAPER cohort, never add old balances"}
    os.makedirs(directory, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    with os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)
    return path

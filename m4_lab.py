"""Prospective paper experiment: isolate inherited M4; never fabricate a sale."""
import copy
import json
import math
import os
from datetime import datetime, timezone
from exit_watchdog import wallet_fork

MINT = "HciAVS1urBtboqhLe59HWiMeeN2McEd6y8h4HGkrpump"
SOURCE = "fomo_lab_early_control_r1.json"
CONTROL = "fomo_lab_m4_control_r1.json"
RECOVERY = "fomo_lab_m4_recovery_r1.json"
MARKER = "fomo_lab_m4_fork_r1.json"


def is_quarantined(position):
    return (position.get("chain") == "solana" and position.get("address") == MINT
            and position.get("m4_quarantine") is True)


def write(path, state):
    with open(path + ".tmp", "w") as handle:
        json.dump(state, handle, indent=2, allow_nan=False)
    os.replace(path + ".tmp", path)


@wallet_fork([SOURCE, CONTROL, RECOVERY, MARKER])
def bootstrap():
    present = [os.path.exists(p) for p in (CONTROL, RECOVERY, MARKER)]
    if all(present):
        return False
    if any(present):
        raise ValueError("Bifurcacion M4 incompleta; restaurar, no reiniciar")
    with open(SOURCE) as handle:
        seed = json.load(handle)
    if seed.get("version") != 1:
        raise ValueError("Fuente M4 incompatible")
    targets = [p for p in seed["positions"] if p.get("chain") == "solana"
               and p.get("address") == MINT and p.get("quote_status") != "OK"]
    if len(targets) != 1:
        raise ValueError("Requiere una M4 heredada sin valoracion verificable")
    known = seed["cash"] + seed["reserve"] + sum(
        p["mark_net"] for p in seed["positions"] if p.get("quote_status") == "OK")
    if not math.isfinite(known) or known <= 75:
        raise ValueError("Capital conocido insuficiente para laboratorio M4")
    baseline = {"at": datetime.now(timezone.utc).isoformat(), "source": SOURCE,
                "verified_component": known, "total_equity": None,
                "cash": seed["cash"], "reserve": seed["reserve"],
                "unknown": sum(p.get("quote_status") != "OK" for p in seed["positions"])}
    for arm, path in (("control", CONTROL), ("recovery", RECOVERY)):
        state = copy.deepcopy(seed)
        state["m4_experiment"] = {"version": "m4-r1", "arm": arm}
        state["m4_baseline"] = baseline
        if arm == "recovery":
            for p in state["positions"]:
                if p.get("chain") == "solana" and p.get("address") == MINT:
                    p["m4_quarantine"] = True
                    p["m4_quarantined_at"] = baseline["at"]
        write(path, state)
    write(MARKER, baseline)
    return True


def run(ranking, simulator):
    if bootstrap():
        print("LAB M4 INICIO: misma copia e historial; decisiones desde proxima lectura; NO sumar")
        return
    from candle_lab import guard
    rows = {}
    for arm, path in (("control", CONTROL), ("recovery", RECOVERY)):
        simulator(ranking, path, "LAB M4 " + arm.upper(), confirm=True,
                  entry_mode="early", entry_guard=guard(False, "early", "LAB M4 " + arm),
                  quarantine_m4=arm == "recovery")
        with open(path) as handle:
            state = json.load(handle)
        obs = state["observations"][-1]
        rows[arm] = {"known_component": obs["verified_component"],
                     "known_change": obs["verified_component"] - state["m4_baseline"]["verified_component"],
                     "total_equity": obs["estimated_equity"],
                     "unknown": obs["unverified_quotes"], "open": obs["open"],
                     "closed": obs["closed"], "cash": state["cash"], "reserve": state["reserve"]}
    rows["total_equity_advantage"] = None
    print("LAB M4 COMPARACION " + json.dumps(rows, allow_nan=False)
          + " | componente conocido NO es rentabilidad total; M4 permanece abierta")

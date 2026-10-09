"""Isolated prospective comparison of a 60m versus 24h pair-age ceiling."""
import copy
import json
import math
import os
from datetime import datetime, timezone
from exit_watchdog import wallet_fork
from m4_lab import RECOVERY as SOURCE, write

CONTROL = "fomo_lab_rebound_control_r1.json"
EXTENDED = "fomo_lab_rebound_extended_r1.json"
MARKER = "fomo_lab_rebound_fork_r1.json"


@wallet_fork([SOURCE, CONTROL, EXTENDED, MARKER])
def bootstrap():
    present = [os.path.exists(p) for p in (CONTROL, EXTENDED, MARKER)]
    if all(present):
        return False
    if any(present):
        raise ValueError("Bifurcacion rebound incompleta; restaurar, no reiniciar")
    with open(SOURCE) as handle:
        seed = json.load(handle)
    if seed.get("version") != 1 or seed.get("m4_experiment") != {"version": "m4-r1", "arm": "recovery"}:
        raise ValueError("Fuente rebound incompatible")
    known = seed["cash"] + seed["reserve"] + sum(p["mark_net"] for p in seed["positions"] if p.get("quote_status") == "OK")
    if not math.isfinite(known) or known <= 75 or seed.get("risk_control", {}).get("halted_at"):
        raise ValueError("Capital conocido insuficiente o freno vigente; no reiniciar")
    baseline = {"at": datetime.now(timezone.utc).isoformat(), "source": SOURCE,
                "known_component": known, "cash": seed["cash"], "reserve": seed["reserve"],
                "closed": len(seed["closed"]), "open": len(seed["positions"])}
    for arm, path in (("control", CONTROL), ("extended", EXTENDED)):
        state = copy.deepcopy(seed)
        state["rebound_experiment"] = {"version": "age-r1", "arm": arm}
        state["rebound_baseline"] = baseline
        write(path, state)
    write(MARKER, baseline)
    return True


def run(ranking, simulator):
    if bootstrap():
        print("LAB REBOUND INICIO: misma copia; edad maxima 60m vs 24h; decisiones desde proxima lectura; NO sumar")
        return
    rows = {}
    for arm, path, ceiling in (("control", CONTROL, 60), ("extended", EXTENDED, 1440)):
        simulator(ranking, path, "LAB REBOUND " + arm.upper(), confirm=True,
                  entry_mode="early", quarantine_m4=True, max_pair_age_minutes=ceiling)
        with open(path) as handle:
            state = json.load(handle)
        obs = state["observations"][-1]
        rows[arm] = {"known_component": obs["verified_component"],
                     "known_change": obs["verified_component"] - state["rebound_baseline"]["known_component"],
                     "total_equity": obs["estimated_equity"], "unknown": obs["unverified_quotes"],
                     "open": obs["open"], "closed_since_fork": obs["closed"] - state["rebound_baseline"]["closed"]}
    print("LAB REBOUND COMPARACION " + json.dumps(rows, allow_nan=False)
          + " | precios y salidas virtuales; patrimonio total desconocido si hay cotizaciones pendientes")

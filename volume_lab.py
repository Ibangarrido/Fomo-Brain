"""Prospective virtual comparison of absolute entry volume; never reset accounts."""
import copy
import json
import math
import os
from datetime import datetime, timezone

MIN_VOLUME_5M = 5000.0
SOURCE = "fomo_lab_ratio_impulse_60_r1.json"
MARKER = "fomo_lab_volume_fork_r1.json"
ARMS = ("control", "volume")


def filename(arm):
    return f"fomo_lab_volume_impulse_{arm}_r1.json"


def bootstrap():
    present = [os.path.exists(filename(arm)) for arm in ARMS]
    if all(present):
        return False
    if any(present) or os.path.exists(MARKER):
        raise ValueError("Carteras volumen incompletas; restaurar memoria, no reiniciar")
    with open(SOURCE) as handle:
        seed = json.load(handle)
    if (seed.get("version") != 1 or seed.get("ratio_experiment") !=
            {"mode": "impulse", "min_buy_ratio": .60, "version": "ratio-r1"}):
        raise ValueError("Fuente IMPULSO60 incompatible")
    if not seed.get("observations") or not seed["observations"][-1].get("valuation_complete"):
        raise ValueError("Fuente sin valoracion completa; aplazar copia")
    now = datetime.now(timezone.utc).isoformat()
    baseline = {"at": now, "source": SOURCE,
                "equity": seed["observations"][-1]["estimated_equity"],
                "realized": sum(x["profit"] for x in seed["closed"]),
                "cash": seed["cash"], "reserve": seed["reserve"],
                "open": len(seed["positions"])}
    for arm in ARMS:
        state = copy.deepcopy(seed)
        state["volume_baseline"] = baseline
        state["volume_experiment"] = {"version": "volume-r1", "arm": arm,
                                      "min_volume_5m_usd": MIN_VOLUME_5M if arm == "volume" else None}
        path = filename(arm)
        with open(path + ".tmp", "w") as handle:
            json.dump(state, handle, indent=2)
        os.replace(path + ".tmp", path)
    with open(MARKER + ".tmp", "w") as handle:
        json.dump({"version": "volume-r1", "at": now,
                   "files": [filename(arm) for arm in ARMS]}, handle)
    os.replace(MARKER + ".tmp", MARKER)
    print(f"LAB VOLUMEN INICIO | {now} | patrimonio={baseline['equity']:.2f}"
          f" | realizado={baseline['realized']:+.2f} | misma copia; NO nuevos 100 EUR")
    return True


def volume_guard(token):
    try:
        volume = float(token.get("vol5m"))
    except (TypeError, ValueError):
        return "LAB volumen-r1: volumen5m ausente"
    if not math.isfinite(volume) or volume < MIN_VOLUME_5M:
        return "LAB volumen-r1: volumen5m < 5000 USD o invalido"
    token["entry_policy_suffix"] = "+volume-r1"
    return None


def run(ranking, simulator):
    if bootstrap():
        print("LAB VOLUMEN: copia inicial; decisiones desde siguiente lectura")
        return
    for arm in ARMS:
        simulator(ranking, filename(arm), f"LAB VOLUME IMPULSE {arm.upper()} r1",
                  confirm=True, entry_mode="impulse", min_buy_ratio=.60,
                  entry_guard=volume_guard if arm == "volume" else None)

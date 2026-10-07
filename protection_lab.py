"""Prospective virtual protection comparison; copy existing balances once, never reset."""
import copy
import json
import os
from datetime import datetime, timezone
from exit_watchdog import wallet_fork

MODES = ("early", "impulse")
ARMS = ("control", "protect")


def filename(mode, arm):
    return f"fomo_lab_protect_{mode}_{arm}_r1.json"


@wallet_fork([f"fomo_lab_ratio_{mode}_60_r1.json" for mode in MODES]
             + [filename(mode, arm) for mode in MODES for arm in ARMS])
def bootstrap():
    paths = [filename(mode, arm) for mode in MODES for arm in ARMS]
    present = [os.path.exists(path) for path in paths]
    if all(present):
        return False
    if os.path.exists("fomo_lab_protect_fork_r1.json") or any(present):
        raise ValueError("Faltan carteras de proteccion; restaurar artefacto, no reiniciar")
    now = datetime.now(timezone.utc).isoformat()
    seeds = {}
    # Validate every source before creating any fork.
    for mode in MODES:
        source = f"fomo_lab_ratio_{mode}_60_r1.json"
        with open(source) as handle:
            seed = json.load(handle)
        if (seed.get("version") != 1 or seed.get("ratio_experiment") !=
                {"mode": mode, "min_buy_ratio": .60, "version": "ratio-r1"}):
            raise ValueError("Fuente ratio 60 incompatible")
        if not seed.get("observations") or not seed["observations"][-1].get("valuation_complete"):
            raise ValueError("Fuente sin valoracion completa; aplazar bifurcacion")
        seeds[mode] = (source, seed)
    for mode, (source, seed) in seeds.items():
        baseline = {"at": now, "source": source,
                    "equity": seed["observations"][-1]["estimated_equity"],
                    "realized": sum(x["profit"] for x in seed["closed"]),
                    "cash": seed["cash"], "reserve": seed["reserve"],
                    "open": len(seed["positions"])}
        for arm in ARMS:
            state = copy.deepcopy(seed)
            state["protection_experiment"] = {"version": "protect-r1", "mode": mode,
                                             "enabled": arm == "protect"}
            state["protection_baseline"] = baseline
            # Do not reuse earlier peaks to trigger the new rule retrospectively.
            for pos in state["positions"]:
                pos.pop("profit_protection_armed", None)
                pos.pop("profit_protection_armed_at", None)
                pos["protection_fork_at"] = now
            path = filename(mode, arm)
            with open(path + ".tmp", "w") as handle:
                json.dump(state, handle, indent=2)
            os.replace(path + ".tmp", path)
        print(f"LAB PROTECCION INICIO {mode.upper()} | {now} | patrimonio={baseline['equity']:.2f}"
              f" | realizado={baseline['realized']:+.2f} | misma copia para ambos brazos; NO sumar")
    with open("fomo_lab_protect_fork_r1.json.tmp", "w") as handle:
        json.dump({"version": "protect-r1", "at": now, "files": paths}, handle)
    os.replace("fomo_lab_protect_fork_r1.json.tmp", "fomo_lab_protect_fork_r1.json")
    return True


def run(ranking, simulator):
    print("LAB PROTECCION r1: control vs armar +12% neto / salir <=+2%; fills no garantizados.")
    if bootstrap():
        print("LAB PROTECCION: copia inicial; decisiones desde la proxima lectura.")
        return
    for mode in MODES:
        for arm in ARMS:
            simulator(ranking, filename(mode, arm),
                      f"LAB PROTECT {mode.upper()} {arm.upper()} r1",
                      confirm=True, entry_mode=mode, min_buy_ratio=.60,
                      profit_protection=arm == "protect")

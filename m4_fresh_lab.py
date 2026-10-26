"""Create a fresh M4 PAPER experiment without altering historical portfolios.

Only the new wallet starts at 100 EUR. Original M4, logs, positions and
learning records remain unchanged. No actual trading or wallet signing.
"""
import copy
import json
import os
from datetime import datetime, timezone

FRESH = "fomo_lab_m4_fresh_r1.json"
ARCHIVE = "fomo_lab_m4_fresh_manifest_r1.json"

def bootstrap(source="fomo_lab_early_control_r1.json", destination=FRESH, manifest=ARCHIVE):
    # Fail closed if only one file exists: never overwrite a prior experiment.
    if os.path.exists(destination) or os.path.exists(manifest):
        if not (os.path.exists(destination) and os.path.exists(manifest)):
            raise ValueError("M4 fresh fork incomplete; restore missing file")
        with open(manifest, encoding="utf-8") as handle:
            record=json.load(handle)
        if record.get("destination") != destination or record.get("source") != source:
            raise ValueError("M4 fresh fork provenance mismatch")
        return False
    with open(source, encoding="utf-8") as handle:
        old=json.load(handle)
    if old.get("version") != 1 or not isinstance(old.get("positions"), list):
        raise ValueError("Invalid historical source: no reset performed")
    now=datetime.now(timezone.utc).isoformat()
    # Fresh independent 100 EUR baseline, NOT an update to old P&L.
    fresh=copy.deepcopy(old)
    fresh.update({"cash":100.0,"reserve":0.0,"positions":[],"closed":[],
                  "seen":[],"observations":[],"version":1})
    for key in ("risk_control","unknown_isolation_epoch","m4_isolation_history",
                "m4_reference_valuation","last_m4_diagnostic"):
        fresh.pop(key,None)
    fresh["m4_fresh_experiment"]={"version":"fresh-r1","created_at":now,
        "source":source,"independent_start_eur":100.0,
        "historical_positions_removed_from_fresh_copy_only":len(old["positions"]),
        "not_a_sale":True,"not_a_recovery_of_historical_capital":True}
    record={"version":"fresh-r1","source":source,"destination":destination,
            "created_at":now,"source_open_positions":len(old["positions"]),
            "source_closed_positions":len(old.get("closed",[])),
            "source_preserved":True,"original_accounting_unchanged":True}
    # Exclusive create: never overwrite historical or existing fork files.
    def create(path, value):
        with open(path,"x",encoding="utf-8") as handle:
            json.dump(value,handle,indent=2,allow_nan=False)
    create(destination,fresh)
    create(manifest,record)
    return True

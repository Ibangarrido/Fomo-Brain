"""Prospective paper experiment: isolate inherited M4; never fabricate a sale."""
import copy
import json
import math
import os
from datetime import datetime, timezone
from exit_watchdog import wallet_fork, wallet_lock

MINT = "HciAVS1urBtboqhLe59HWiMeeN2McEd6y8h4HGkrpump"
SOURCE = "fomo_lab_early_control_r1.json"
CONTROL = "fomo_lab_m4_control_r1.json"
RECOVERY = "fomo_lab_m4_recovery_r1.json"
MARKER = "fomo_lab_m4_fork_r1.json"


def m4_diagnostic(state, audit=None, now=None):
    """Explain the inherited mark using recent exact-quantity evidence, never a fill."""
    now = now or datetime.now(timezone.utc)
    positions = [p for p in state.get("positions", [])
                 if p.get("chain") == "solana" and p.get("address") == MINT]
    if len(positions) != 1:
        return {"status": "NO_SINGLE_M4_POSITION", "net_value_usdc": None}
    pos = positions[0]
    result = {"status": "NO_RECENT_QUANTITY_QUOTE", "quote_status": pos.get("quote_status"),
              "historical_mark": pos.get("mark_net"),
              "historical_mark_is_current": pos.get("quote_status") == "OK",
              "historical_mark_unit": "paper model units; not USDC",
              "historical_mark_at": pos.get("last_quote_at"),
              "quantity": pos.get("quantity"), "gross_quote_usdc": None,
              "net_value_usdc": None, "execution_verified": False,
              "costs_complete": False, "fx_applied": False}
    result["market_blocker"] = pos.get("quote_error") if pos.get("quote_status") != "OK" else None
    result["indicative_liquidity_usd"] = pos.get("indicative_liquidity")
    try:
        result["historical_mark_age_seconds"] = max(0, (now - datetime.fromisoformat(
            pos["last_quote_at"])).total_seconds())
    except (KeyError, ValueError, TypeError):
        result["historical_mark_age_seconds"] = None
    if audit is None:
        try:
            with open("fomo_quote_audit.json") as handle:
                audit = json.load(handle)
        except (OSError, ValueError):
            return result
    if not isinstance(audit, dict):
        return result
    candidates = []
    records = audit.get("records")
    if not isinstance(records, list):
        return result
    for record in records:
        try:
            if (record.get("kind") != "JUPITER" or record.get("chain") != "solana"
                    or record.get("address") != MINT or record.get("quantity") != pos.get("quantity")
                    or record.get("status") != "QUOTE_ONLY"):
                continue
            received = datetime.fromisoformat(record["received_at"])
            age = (now - received).total_seconds()
            value = record["expected_out_usdc"]
            if (not 0 <= age <= 120 or type(value) not in (int, float)
                    or not math.isfinite(value) or value <= 0):
                continue
            candidates.append((received, age, value))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    if candidates:
        received, age, value = max(candidates, key=lambda row: row[0])
        result.update(status="RECENT_GROSS_QUOTE_ONLY", gross_quote_usdc=value,
                      quote_received_at=received.isoformat(), quote_age_seconds=age)
    return result


def report_snapshot(path):
    """Persist report evidence under the same lock as exit writes; preserve accounting."""
    with wallet_lock(path):
        with open(path) as handle:
            state = json.load(handle)
        state["last_m4_diagnostic"] = {
            "reported_at": datetime.now(timezone.utc).isoformat(),
            **m4_diagnostic(state)}
        write(path, state)
        return state


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
        state = report_snapshot(path)
        obs = state["observations"][-1]
        rows[arm] = {"known_component": obs["verified_component"],
                     "known_change": obs["verified_component"] - state["m4_baseline"]["verified_component"],
                     "total_equity": obs["estimated_equity"],
                     "unknown": obs["unverified_quotes"], "open": obs["open"],
                     "closed": obs["closed"], "cash": state["cash"], "reserve": state["reserve"]}
        rows[arm]["m4_diagnostic"] = state["last_m4_diagnostic"]
    rows["total_equity_advantage"] = None
    print("LAB M4 COMPARACION " + json.dumps(rows, allow_nan=False)
          + " | componente conocido NO es rentabilidad total; M4 permanece abierta")


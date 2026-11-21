"""PAPER2-only quarantine of explicitly verified unexecutable positions.

A quarantine is NOT a sale, write-off, or claim of zero value.
"""
import copy

def quarantine_exact_positions(state, keys, evidence):
    if state.get("portfolio_id") != "clean-v1-paper-2":
        raise ValueError("Only PAPER2 can be quarantined")
    if not isinstance(keys, (list, tuple)) or not keys or len(keys) != len(set(keys)):
        raise ValueError("Explicit unique position keys required")
    positions = state["positions"]
    isolated = state.setdefault("isolated_positions", {})
    if not isinstance(isolated, dict):
        raise ValueError("Invalid quarantine ledger")
    for key in keys:
        if key not in positions or key in isolated:
            raise ValueError("Position absent or already quarantined: " + str(key))
        proof = evidence.get(key) if isinstance(evidence, dict) else None
        if not isinstance(proof, dict) or proof.get("exit_unexecutable") is not True or not proof.get("source"):
            raise ValueError("Specific documented non-executable exit evidence required")
    result = copy.deepcopy(state)
    for key in keys:
        pos = result["positions"].pop(key)
        result["isolated_positions"][key] = {
            **pos, "isolation_status": "UNEXECUTABLE_NOT_SOLD",
            "isolation_evidence": copy.deepcopy(evidence[key]),
            "realizable_value_eur": None,
        }
    # cash, closed, cost basis and trade IDs remain exactly unchanged
    return result

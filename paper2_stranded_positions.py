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

def quarantine_persistent_low_liquidity(state, run_id, samples=None, now=None, min_gap_seconds=3600):
    """Quarantine only after fresh low-liquidity observations in separate runs.

    A low-liquidity quote is an administrative risk proxy, never an executed exit.
    """
    import math
    if state.get("portfolio_id") != "clean-v1-paper-2":
        raise ValueError("PAPER2 only")
    if not run_id or not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now):
        raise ValueError("Run ID and finite current time required")
    from brain_clean_v1 import MIN_LIQ, MAX_AGE_SECONDS
    quotes = {q["key"]: q for q in (samples or []) if isinstance(q, dict) and "key" in q}
    observations = state.setdefault("stranded_observations", {})
    quarantined = []
    for key in list(state["positions"]):
        q = quotes.get(key)
        if q is None:
            observations.pop(key, None)
            continue
        ts, liq, price = q.get("ts"), q.get("liquidity"), q.get("price")
        valid = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                    for v in (ts, liq, price))
        if not valid or ts > now + 60 or ts < now - MAX_AGE_SECONDS or price <= 0 or liq <= 0:
            observations.pop(key, None)
            continue
        if liq >= MIN_LIQ:
            observations.pop(key, None)
            continue
        previous = observations.get(key)
        if previous is None:
            observations[key] = {"run_id": str(run_id), "ts": ts, "liquidity_usd": liq}
            continue
        if previous["run_id"] == str(run_id) or ts < previous["ts"] + min_gap_seconds:
            continue
        proof = {key: {"exit_unexecutable": True,
            "source": "PAPER2_TWO_RUN_FRESH_LOW_LIQUIDITY_PROXY_NOT_ROUTE_PROOF",
            "first_run": previous["run_id"], "second_run": str(run_id),
            "first_ts": previous["ts"], "second_ts": ts,
            "first_liquidity_usd": previous["liquidity_usd"],
            "second_liquidity_usd": liq}}
        changed = quarantine_exact_positions(state, [key], proof)
        state.clear()
        state.update(changed)
        observations = state["stranded_observations"]
        observations.pop(key, None)
        quarantined.append(key)
    return quarantined


def quarantine_persistent_missing_quotes(state, samples, run_id, now, min_gap_seconds=3600):
    """Release PAPER2 slots only after two independent runs with absent quotes.

    This is administrative isolation, not evidence of a sale or zero value.
    """
    import math
    if state.get("portfolio_id") != "clean-v1-paper-2":
        raise ValueError("PAPER2 only")
    if not run_id or not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now):
        raise ValueError("Valid run and observation time required")
    quotes = {s["key"]: s for s in samples}
    observations = state.setdefault("stranded_missing_quote_observations", {})
    quarantined = []
    for key in list(state["positions"]):
        q = quotes.get(key)
        from brain_clean_v1 import MAX_AGE_SECONDS
        def valid_number(v):
            return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        missing = (q is None or not all(valid_number(q.get(k)) for k in ("price", "liquidity", "ts"))
                   or q["price"] <= 0 or q["liquidity"] <= 0
                   or q["ts"] < now - MAX_AGE_SECONDS or q["ts"] > now + 60)
        if not missing:
            observations.pop(key, None)
            continue
        previous = observations.get(key)
        if previous is None:
            observations[key] = {"run_id": str(run_id), "ts": now}
            continue
        if str(previous["run_id"]) == str(run_id) or now < previous["ts"] + min_gap_seconds:
            continue
        proof = {key: {"exit_unexecutable": True,
            "source": "PAPER2_TWO_RUN_MISSING_QUOTES_ADMINISTRATIVE_ONLY",
            "first_run": previous["run_id"], "second_run": str(run_id),
            "first_ts": previous["ts"], "second_ts": now,
            "note": "No valid quote; sale and recoverable value remain unverified"}}
        changed = quarantine_exact_positions(state, [key], proof)
        state.clear()
        state.update(changed)
        observations = state["stranded_missing_quote_observations"]
        observations.pop(key, None)
        quarantined.append(key)
    return quarantined

"""Pure PAPER decision journal; no trading or portfolio writes."""
import hashlib
import json
import math

HORIZONS = (300, 900, 1800, 3600, 14400)

def positive(x):
    return type(x) in (int, float) and math.isfinite(x) and x > 0

def record(journal, *, mint, chain, timestamp, price, decision, reason, features, strategy):
    if not all(isinstance(x,str) and x.strip() for x in (mint,chain,decision,reason,strategy)):
        raise ValueError("missing identity")
    if not positive(timestamp) or not positive(price):
        raise ValueError("invalid timestamp or price")
    if not isinstance(features, dict):
        raise ValueError("features must be a mapping")
    key = hashlib.sha256(json.dumps([chain,mint,timestamp,strategy], separators=(",",":")).encode()).hexdigest()
    row = json.loads(json.dumps(dict(mint=mint,chain=chain,timestamp=timestamp,price=price,
        decision=decision,reason=reason,features=features,strategy=strategy), allow_nan=False))
    if key in journal:
        if journal[key]["decision"] != row:
            raise ValueError("conflicting duplicate decision")
        return key
    journal[key] = {"decision":row,"outcomes":{}}
    return key

def observe(journal, key, *, timestamp, price, observed_at, tolerance=60):
    row = journal[key]
    if not all(positive(x) for x in (timestamp,price,observed_at)) or timestamp > observed_at:
        raise ValueError("invalid observation")
    if type(tolerance) is not int or not 0 <= tolerance <= 60:
        raise ValueError("invalid tolerance")
    elapsed = timestamp - row["decision"]["timestamp"]
    for horizon in HORIZONS:
        if horizon <= elapsed <= horizon + tolerance:
            result = dict(timestamp=timestamp, price=price,
                gross_return_pct=100*(price/row["decision"]["price"]-1))
            if not math.isfinite(result["gross_return_pct"]):
                raise ValueError("invalid return")
            slot = str(horizon)
            if slot in row["outcomes"] and row["outcomes"][slot] != result:
                raise ValueError("conflicting outcome")
            if slot not in row["outcomes"]:
                row["outcomes"][slot] = result
                row.setdefault("outcome_received_at", {})[slot] = observed_at
            return slot
    return None


def risk_memory(journal, *, chain, mint, as_of, ttl=86400):
    """Read-only risk history from recorded decisions; alerts are not fraud findings."""
    if not all(isinstance(x,str) and x.strip() for x in (chain,mint)) or not positive(as_of) or not positive(ttl):
        raise ValueError("invalid risk query")
    evidence={}
    for key,item in journal.items():
        row=item["decision"]
        if (row["chain"],row["mint"])!=(chain,mint):
            continue
        t=row["timestamp"]
        if not positive(t) or not 0<=as_of-t<=ttl:
            continue
        features=row["features"]
        alert=features.get("risk_alert")
        if alert not in ("REPEAT_CRASH_ALERT","LIQUIDITY_DROP_ALERT"):
            continue
        pool=features.get("pair")
        if not isinstance(pool,str) or not pool:
            continue
        identity=(pool,t,alert)
        evidence.setdefault(identity,dict(decision_id=key,timestamp=t,pair=pool,alert=alert))
    rows=sorted(evidence.values(),key=lambda r:(r["timestamp"],r["pair"],r["alert"]))
    return dict(status="RISK_REVIEW" if rows else "NO_RECENT_RECORDED_ALERT",
                evidence=rows,scope="PAPER_OBSERVATION_ONLY",orders=[],fraud_verified=False)


def discard_review(journal, *, as_of, horizon=1800, decisions=("HOLD","BLOCK","REJECT","DISCARD")):
    """Descriptive matured outcomes only; legacy unknown receipt times excluded."""
    if not positive(as_of) or horizon not in HORIZONS:
        raise ValueError("invalid review cutoff or horizon")
    counts=dict(matured=0, pending=0, rally_2x=0, rally_5x=0, rally_10x=0, crash_50pct=0)
    by_reason={}
    slot=str(horizon)
    for item in journal.values():
        row=item["decision"]
        if row["decision"].upper() not in decisions or row["timestamp"]>as_of:
            continue
        outcome=item["outcomes"].get(slot)
        receipt=item.get("outcome_received_at",{}).get(slot)
        if not outcome or not positive(receipt) or not row["timestamp"]+horizon<=outcome["timestamp"]<=receipt<=as_of:
            counts["pending"]+=1
            continue
        ret=outcome["gross_return_pct"]
        if not math.isfinite(ret):
            counts["pending"]+=1
            continue
        counts["matured"]+=1
        group=by_reason.setdefault(row["reason"],dict(matured=0,rally_2x=0,crash_50pct=0))
        group["matured"]+=1
        for key,threshold in (("rally_2x",100),("rally_5x",400),("rally_10x",900)):
            counts[key]+=int(ret>=threshold)
        counts["crash_50pct"]+=int(ret<=-50)
        group["rally_2x"]+=int(ret>=100)
        group["crash_50pct"]+=int(ret<=-50)
    return dict(counts=counts,by_reason=by_reason,horizon=horizon,scope="DESCRIPTIVE_PRICE_ONLY",orders=[])

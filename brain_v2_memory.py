"""Pure PAPER decision journal; no trading or portfolio writes."""
import hashlib
import json
import math

HORIZONS = (300, 900, 3600, 14400)

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
            row["outcomes"][slot] = result
            return slot
    return None

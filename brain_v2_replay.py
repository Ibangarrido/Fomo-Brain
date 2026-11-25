"""Read-only PAPER decision replay, no counterfactual executable fills."""
import math
from collections import Counter

def review(records, *, as_of, horizon=3600, tolerance=60):
    def num(x):
        return type(x) in (int,float) and math.isfinite(x)
    if not all(num(x) for x in (as_of,horizon,tolerance)) or horizon<=0 or not 0<=tolerance<horizon:
        raise ValueError("invalid window")
    seen={}
    results=[]
    for r in records:
        key=r["id"]
        if not isinstance(key,str) or not key:
            raise ValueError("invalid id")
        if key in seen:
            if seen[key]!=r: raise ValueError("conflicting record")
            continue
        seen[key]=r
        t,p=r.get("timestamp"),r.get("price")
        if not num(t) or t>as_of or not num(p) or p<=0:
            continue
        if r.get("decision") not in ("HOLD","REJECT","WATCH_ONLY"):
            continue
        reason=str(r.get("reason") or "UNKNOWN_REASON")
        status="PENDING" if as_of<t+horizon+tolerance else "MISSING_OUTCOME"
        ret=None
        candidates=[]
        for o in r.get("observations",[]):
            ot,op,known=o.get("timestamp"),o.get("price"),o.get("observed_at")
            if o.get("verified") is True and all(num(x) for x in (ot,op,known)) and op>0 and t+horizon<=ot<=t+horizon+tolerance and ot<=known<=as_of:
                candidates.append((ot,op))
        if candidates:
            ot=min(x[0] for x in candidates)
            prices={p for ts,p in candidates if ts==ot}
            if len(prices)!=1: raise ValueError("conflicting outcome")
            ret=(prices.pop()/p-1)*100
            status="RALLY_AFTER_DISCARD" if ret>=20 else "DROP_AFTER_DISCARD" if ret<=-20 else "NEUTRAL"
        results.append(dict(id=key,reason=reason,status=status,gross_price_change_pct=ret))
    return dict(scope="DESCRIPTIVE_PAPER_ONLY",rows=results,counts=dict(Counter(r["status"] for r in results)),by_reason={reason:dict(Counter(r["status"] for r in results if r["reason"]==reason)) for reason in sorted({r["reason"] for r in results})},orders=[])

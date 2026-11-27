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


def recurrence(current, history, *, as_of):
    """Identity and theme comparison only; no fraud or predictive inference."""
    def identity(r):
        chain, address = r.get("chain"), r.get("mint")
        if not all(isinstance(v,str) and v.strip() for v in (chain,address)):
            return None
        chain=chain.strip().lower()
        if chain in ("bsc","bnb","56","bnb chain"):
            chain="bsc"
        if chain in ("bsc","ethereum","base"):
            address=address.lower()
        return chain,address
    def known(r):
        t,k=r.get("timestamp"),r.get("observed_at")
        return all(type(v) in (int,float) and math.isfinite(v) for v in (t,k)) and 0<t<=k<=as_of
    if not isinstance(as_of,(int,float)) or not math.isfinite(as_of) or not known(current) or not identity(current):
        return dict(status="UNKNOWN",matches=[],orders=[])
    def theme(r):
        v=r.get("theme")
        return v.strip().casefold() if isinstance(v,str) else ""
    matches={}
    for r in history:
        if not known(r) or r["observed_at"]>current["timestamp"] or r["timestamp"]>=current["timestamp"] or not identity(r):
            continue
        same=identity(r)==identity(current)
        related=bool(theme(current)) and theme(r)==theme(current)
        if not (same or related):
            continue
        key=(*identity(r),r["timestamp"])
        matches[key]=dict(chain=key[0],mint=key[1],timestamp=key[2],relation="SAME_CONTRACT" if same else "THEME_MATCH_ONLY")
    return dict(status="MATCHES" if matches else "NO_RECORDED_MATCH",matches=[matches[k] for k in sorted(matches)],scope="DESCRIPTIVE_PAPER_ONLY",orders=[])

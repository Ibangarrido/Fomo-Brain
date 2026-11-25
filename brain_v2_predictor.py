"""PAPER ONLY descriptive analogs; never an entry filter or probability."""
import math

def describe(query, cases, *, as_of, horizon=3600, separation=86400):
    def finite(x):
        return type(x) in (int,float) and math.isfinite(x)
    if not isinstance(query,(list,tuple)) or not query or not all(finite(x) for x in query):
        raise ValueError("invalid normalized features")
    if not all(finite(x) for x in (as_of,horizon,separation)) or horizon<=0 or separation<horizon:
        raise ValueError("invalid temporal scope")
    eligible=[]
    seen={}
    for c in cases:
        t,end,ret=c.get("timestamp"),c.get("outcome_at"),c.get("return_pct")
        f=c.get("features")
        ident=c.get("id")
        if not isinstance(ident,str) or not ident or not all(finite(x) for x in (t,end,ret)):
            continue
        if end != t+horizon or end>=as_of or c.get("verified") is not True:
            continue
        if not isinstance(f,(list,tuple)) or len(f)!=len(query) or not all(finite(x) for x in f):
            continue
        row=(t,end,ret,tuple(f))
        if ident in seen:
            if seen[ident]!=row:
                raise ValueError("conflicting analog")
            continue
        seen[ident]=row
        distance=math.dist(query,f)
        if math.isfinite(distance):
            eligible.append((distance,t,ident,end,ret))
    selected=[]
    for distance,t,ident,end,ret in sorted(eligible):
        if all(abs(t-r["timestamp"])>=separation for r in selected):
            selected.append(dict(id=ident,timestamp=t,outcome_at=end,distance=distance,return_pct=ret))
        if len(selected)==10:
            break
    result=dict(scope="DESCRIPTIVE_ONLY",count=len(selected),cases=selected,entry_filter=False)
    if len(selected)<8:
        return dict(result,status="INSUFFICIENT_HISTORY",fractions=None)
    n=len(selected)
    counts=dict(rally=sum(r["return_pct"]>=20 for r in selected),
                drop=sum(r["return_pct"]<=-20 for r in selected))
    counts["neutral"]=n-counts["rally"]-counts["drop"]
    return dict(result,status="DESCRIPTIVE_ANALOGS",fractions={k:v/n for k,v in counts.items()})

"""Offline comparison only; never changes active filters."""
import math
from statistics import mean

def evaluate(baseline, challenger, *, as_of, selection_cutoff, min_windows=20):
    def finite(x):
        return type(x) in (int,float) and math.isfinite(x)
    if not finite(as_of) or not finite(selection_cutoff) or selection_cutoff>=as_of or type(min_windows) is not int or min_windows<20:
        raise ValueError("invalid evaluation settings")
    def index(rows):
        out={}
        for r in rows:
            s,e=r["start"],r["end"]
            if not finite(s) or not finite(e) or not selection_cutoff<=s<e<=as_of:
                raise ValueError("invalid evaluation window")
            if r.get("verified") is not True or r.get("costs_included") is not True:
                raise ValueError("unverified result")
            if not finite(r["net_pct"]) or r["net_pct"] < -100 or not finite(r["drawdown_pct"]) or not 0<=r["drawdown_pct"]<=100:
                raise ValueError("invalid metrics")
            k=(s,e)
            if k in out: raise ValueError("duplicate window")
            out[k]=r
        keys=sorted(out)
        if any(a[1]>b[0] for a,b in zip(keys,keys[1:])):
            raise ValueError("overlapping windows")
        return out
    a,b=index(baseline),index(challenger)
    result=dict(scope="PAPER_RESEARCH_ONLY",decision="INSUFFICIENT_EVIDENCE",windows=len(a),changes=[],orders=[])
    if set(a)!=set(b):
        result["decision"]="UNMATCHED_WINDOWS"
        return result
    if len(a)<min_windows: return result
    diffs=[b[k]["net_pct"]-a[k]["net_pct"] for k in a]
    improvement=mean(diffs)
    wins=sum(d>0 for d in diffs)/len(diffs)
    risk_a=max(r["drawdown_pct"] for r in a.values())
    risk_b=max(r["drawdown_pct"] for r in b.values())
    result.update(mean_improvement_pp=improvement,better_window_fraction=wins,baseline_max_window_drawdown_pct=risk_a,challenger_max_window_drawdown_pct=risk_b)
    result["decision"]="REVIEW_CANDIDATE" if improvement>=0.5 and wins>=0.6 and risk_b<=risk_a and mean(r["net_pct"] for r in b.values())>0 else "KEEP_BASELINE"
    return result

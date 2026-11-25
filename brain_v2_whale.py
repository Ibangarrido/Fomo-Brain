"""Classify supplied verified public swap records; no wallet connection."""
import math

def classify(events, *, wallet, mint, now, window=3600):
    if not wallet or not mint or not math.isfinite(now) or window <= 0:
        raise ValueError("invalid scope")
    unique = {}
    for e in events:
        if e.get("wallet") != wallet or e.get("mint") != mint:
            continue
        if e.get("verified") is not True:
            continue
        t, amount = e.get("timestamp"), e.get("usd")
        if type(t) not in (int,float) or type(amount) not in (int,float):
            continue
        if not math.isfinite(t) or not math.isfinite(amount) or amount <= 0 or not now-window <= t <= now:
            continue
        sig, index, side = e.get("signature"), e.get("instruction_index"), e.get("side")
        if not isinstance(sig,str) or not sig or type(index) is not int or index < 0 or side not in ("buy","sell"):
            continue
        key = (sig,index)
        row = (t,amount,side)
        if key in unique and unique[key] != row:
            raise ValueError("conflicting swap evidence")
        unique[key] = row
    buys = [r for r in unique.values() if r[2]=="buy"]
    sells = [r for r in unique.values() if r[2]=="sell"]
    b = math.fsum(r[1] for r in buys)
    s = math.fsum(r[1] for r in sells)
    label = "INSUFFICIENT_EVIDENCE"
    if len(buys) >= 3 and len({r[0] for r in buys}) >= 3 and b >= 100 and b > 2*s:
        label = "ACCUMULATION_WATCH"
    elif len(sells) >= 2 and s >= 100 and s > 2*b:
        label = "DISTRIBUTION_WATCH"
    elif unique:
        label = "MIXED_OR_ISOLATED"
    return dict(label=label,buy_count=len(buys),sell_count=len(sells),buy_usd=b,sell_usd=s,net_usd=b-s)

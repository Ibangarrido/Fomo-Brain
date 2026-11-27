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


def progressive_watch(events, *, chain, wallet, mint, now, window=3600):
    """Read-only progressive accumulation; verified supplied evidence, not ownership proof."""
    if not all(isinstance(v,str) and v.strip() for v in (chain,wallet,mint)) or type(now) not in (int,float) or not math.isfinite(now) or type(window) not in (int,float) or not math.isfinite(window) or window<=0:
        raise ValueError("invalid scope")
    scoped=[]
    for e in events:
        t,k=e.get("timestamp"),e.get("observed_at")
        if e.get("chain")!=chain or e.get("wallet")!=wallet or e.get("mint")!=mint or e.get("verified") is not True:
            continue
        if not all(type(v) in (int,float) and math.isfinite(v) for v in (t,k)) or not now-window<=t<=k<=now:
            continue
        scoped.append(e)
    base=classify(scoped,wallet=wallet,mint=mint,now=now,window=window)
    tx={}
    for e in scoped:
        sig,idx,amount,side=e.get("signature"),e.get("instruction_index"),e.get("usd"),e.get("side")
        if not isinstance(sig,str) or not sig or type(idx) is not int or idx<0 or type(amount) not in (int,float) or not math.isfinite(amount) or amount<=0 or side not in ("buy","sell"):
            continue
        tx[(sig,idx)]=(e["timestamp"],amount,side)
    buys={}
    for (sig,idx),(t,amount,side) in tx.items():
        if side=="buy":
            buys.setdefault(sig,[]).append((t,amount))
    series=sorted((min(t for t,a in rows),math.fsum(a for t,a in rows)) for rows in buys.values())
    progressive=len(series)>=3 and all(a[0]<b[0] and a[1]<=b[1] for a,b in zip(series,series[1:])) and series[-1][1]>series[0][1]
    label="PROGRESSIVE_ACCUMULATION_WATCH" if progressive and base["label"]=="ACCUMULATION_WATCH" else base["label"]
    return dict(**base,pattern=label,distinct_buy_transactions=len(series),scope="PAPER_OBSERVATION_ONLY",ownership_verified=False,orders=[])

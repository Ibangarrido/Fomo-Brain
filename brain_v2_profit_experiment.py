"""Experimental PAPER-only policy; no ledger mutation or orders."""
from brain_v2_guardian import assess as guard, number
from brain_v2_radar import assess as radar
from brain_v2_replay import review
from brain_v2_adaptive import evaluate

def anti_staircase(prices):
    if len(prices)<6 or any(not number(p) or p<=0 for p in prices):
        return "UNKNOWN"
    peak=prices[0]
    crashes=0
    for p in prices[1:]:
        if p<=peak*0.5:
            crashes+=1
            peak=p
        else:
            peak=max(peak,p)
    return "BLOCK" if crashes>=2 else "NO_REPEAT_FLAG"

def profit_lock(entry, price, peak, quote_age, liquidity, route_verified):
    risk=guard(entry,price,quote_age,liquidity,route_verified)
    if risk!="MONITOR": return risk
    if not number(peak) or peak<max(entry,price): return "UNKNOWN_PEAK"
    ratio=peak/entry
    floor=max((f for trigger,f in ((1.2,1.05),(1.5,1.3),(2,1.7),(3,2.5),(5,4.2)) if ratio>=trigger),default=0)
    return "PAPER_EXIT_CANDIDATE" if floor and price/entry<=floor else "MONITOR"

def experiment(*, prices, radar_inputs, records, baseline, challenger, as_of, selection_cutoff):
    pattern=anti_staircase(prices)
    signal=radar(**radar_inputs)
    return dict(scope="PAPER_SHADOW_ONLY",pattern=pattern,
        sniper="WATCH_ONLY" if pattern=="NO_REPEAT_FLAG" and signal=="EARLY_WATCH" else "HOLD",
        shadow={h:review(records,as_of=as_of,horizon=h) for h in (300,900,3600,14400)},
        autotest=evaluate(baseline,challenger,as_of=as_of,selection_cutoff=selection_cutoff),
        orders=[],changes=[])


def staircase_watch(samples, *, as_of):
    """Chronological same-pool observation; repeated recovery/crash, not proof of fraud."""
    import math
    unknown=dict(status="UNKNOWN",cycles=0,orders=[])
    if len(samples)<6 or not number(as_of):
        return unknown
    try:
        identity=tuple(samples[0][k] for k in ("mint","pair","source"))
        if not all(isinstance(x,str) and x for x in identity):
            return unknown
        times=[]; prices=[]
        for s in samples:
            if tuple(s[k] for k in ("mint","pair","source"))!=identity:
                return unknown
            t,p=s["received_at"],s["price_usd"]
            if not number(t) or not number(p) or p<=0 or t<=0 or t>as_of:
                return unknown
            if times and not 0<t-times[-1]<=120:
                return unknown
            times.append(t); prices.append(p)
        if as_of-times[-1]>60:
            return unknown
    except (KeyError,TypeError,ValueError):
        return unknown
    peak=prices[0]; trough=None; cycles=0; crashes=0
    for p in prices[1:]:
        if trough is not None:
            trough=min(trough,p)
            if p/trough>=1.5:
                peak=p; trough=None; cycles+=1
        else:
            peak=max(peak,p)
            if p/peak<=0.5:
                crashes+=1; trough=p
    return dict(status="REPEAT_CRASH_ALERT" if crashes>=2 and cycles>=1 else "WATCH" if crashes else "NO_REPEAT_FLAG",
                cycles=cycles,crashes=crashes,orders=[],scope="OBSERVATION_ONLY")

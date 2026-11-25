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

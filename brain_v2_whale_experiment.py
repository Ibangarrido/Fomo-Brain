"""PAPER WHALE research policy; verified supplied swaps only."""
from brain_v2_whale import classify
from brain_v2_radar import assess as radar
from brain_v2_antirug import assess as risk
from brain_v2_simulator import replay

def watch(*, wallets, events, mint, now, radar_inputs, risk_inputs):
    rows={w:classify(events,wallet=w,mint=mint,now=now) for w in sorted(set(wallets))}
    accum=sum(r["label"]=="ACCUMULATION_WATCH" for r in rows.values())
    distribution=sum(r["label"]=="DISTRIBUTION_WATCH" for r in rows.values())
    signal=radar(**radar_inputs)
    safety=risk(**risk_inputs)
    return dict(scope="PAPER_WHALE_SHADOW",wallets=rows,accumulation_count=accum,
        distribution_count=distribution,radar=signal,risk=safety,
        decision="WATCH_ONLY" if accum>=2 and not distribution and signal=="EARLY_WATCH" and safety.get("decision")=="NO_FLAG_OBSERVED" else "HOLD",orders=[])

def compare_fills(baseline, whale):
    return dict(baseline=replay(baseline,initial=100),whale=replay(whale,initial=100),
                scope="PAPER_RESEARCH_ONLY",orders=[])

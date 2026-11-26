"""Market observation orchestration; no executable quotes or ledger mutation."""
from brain_v2_live import poll
from brain_v2_doctor import diagnose
from brain_v2_antirug import assess
from brain_v2_replay import review
from brain_v2_adaptive import evaluate
from brain_v2_core import cycle

def observe(mints, *, fetcher=None):
    kwargs={} if fetcher is None else {"fetcher":fetcher}
    batch=next(poll(mints,**kwargs))
    return [dict(mint=r["mint"],source_status=r["status"],observations=r["observations"],
                 source_error=r.get("error"),
                 decision="HOLD",reason="NO_VERIFIED_EXECUTION_EVIDENCE",
                 risk=assess(),orders=[]) for r in batch]

def integrated(*, state, previous, now, candidates, journal, health_evidence,
               market_rows, replay_records=(), baseline=(), challenger=(), selection_cutoff=None):
    t=now.timestamp()
    core=cycle(state=state,previous=previous,now=now,candidates=candidates,journal=journal)
    evidence=dict(health_evidence)
    evidence["source_status"]="OK" if market_rows and all(r["source_status"]=="OK" for r in market_rows) else "ERROR"
    doctor=diagnose(health=core["health"],**evidence)
    replay=review(replay_records,as_of=t)
    adaptive=evaluate(baseline,challenger,as_of=t,selection_cutoff=selection_cutoff if selection_cutoff is not None else t-1)
    return dict(scope="PAPER_SHADOW_ONLY",core=core,doctor=doctor,replay=replay,adaptive=adaptive,
                market=market_rows,decision="HOLD",orders=[],changes=[])

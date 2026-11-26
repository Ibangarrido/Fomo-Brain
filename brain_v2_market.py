"""Market observation orchestration; no executable quotes or ledger mutation."""
from brain_v2_live import poll
from brain_v2_solana_bridge import bridge
from brain_v2_doctor import diagnose
from brain_v2_antirug import assess
from brain_v2_replay import review
from brain_v2_adaptive import evaluate
from brain_v2_core import cycle

def compare_sources(sources, *, max_receipt_gap=30, threshold_pct=10):
    """Descriptive token-level comparison, never an executable quote."""
    import math
    try:
        a,b=(sources[k] for k in ("dexscreener","geckoterminal"))
        if any(x["status"]!="OK" for x in (a,b)):
            raise ValueError("missing source")
        p,q=(float(x["data"]["price_usd"]) for x in (a,b))
        t,u=(float(x["received_at"]) for x in (a,b))
        if not all(math.isfinite(x) for x in (p,q,t,u)) or min(p,q)<=0 or min(t,u)<=0 or abs(t-u)>max_receipt_gap:
            raise ValueError("invalid or asynchronous evidence")
    except (KeyError,TypeError,ValueError,OverflowError):
        return dict(status="UNKNOWN",scope="TOKEN_LEVEL_ONLY",executable=False)
    gap=200*(max(p,q)-min(p,q))/max(p,q)/(1+min(p,q)/max(p,q))
    return dict(status="DISCREPANCY" if gap>=threshold_pct else "WITHIN_THRESHOLD",
                gap_pct=gap,scope="TOKEN_LEVEL_ONLY",executable=False,
                liquidity_comparable=False,quote_timestamp_verified=False)

def observe(mints, *, fetcher=None, fallback=None):
    kwargs={} if fetcher is None else {"fetcher":fetcher}
    batch=next(poll(mints,**kwargs))
    # Only default live calls use the public fallback; injected tests stay offline.
    if fallback is None and fetcher is None:
        fallback=bridge
    result=[dict(mint=r["mint"],source_status=r["status"],observations=r["observations"],
                 source_error=r.get("error"),source_http_status=r.get("http_status"),
                 decision="HOLD",reason="NO_VERIFIED_EXECUTION_EVIDENCE",
                 risk=assess(),orders=[]) for r in batch]
    for row in result:
        if fallback is None or row["source_status"] not in ("SOURCE_ERROR","NO_DATA"):
            continue
        try:
            evidence=fallback(row["mint"])
            if evidence.get("mint") != row["mint"]:
                raise ValueError("fallback mint mismatch")
            row["fallback_sources"]=evidence["sources"]
            row["source_comparison"]=compare_sources(evidence["sources"])
        except Exception as exc:
            row["fallback_error"]=type(exc).__name__
        # Fallback evidence is informational; never promote to executable or OK.
    return result

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

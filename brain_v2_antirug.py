"""Read-only risk assessment of supplied verified observations."""
import math

def assess(*, liquidity_usd=None, previous_liquidity_usd=None,
           top10_pct=None, mint_authority_active=None, freeze_authority_active=None,
           route_verified=None, evidence_verified=False, age_seconds=None):
    def valid(x,lo,hi=math.inf):
        return type(x) in (int,float) and math.isfinite(x) and lo<=x<=hi
    risks=[]
    unknown=[]
    if evidence_verified is not True or not valid(age_seconds,0,60):
        return dict(status="UNKNOWN_BLOCK",risks=[],unknown=["UNVERIFIED_OR_STALE_EVIDENCE"],orders=[])
    if not valid(liquidity_usd,0):
        unknown.append("LIQUIDITY")
    elif liquidity_usd<5000:
        risks.append("LOW_LIQUIDITY")
    if not valid(previous_liquidity_usd,1) or not valid(liquidity_usd,0):
        unknown.append("LIQUIDITY_BASELINE")
    elif liquidity_usd<=previous_liquidity_usd*0.7:
        risks.append("LIQUIDITY_DROP")
    if not valid(top10_pct,0,100):
        unknown.append("HOLDER_CONCENTRATION")
    elif top10_pct>=50:
        risks.append("CONCENTRATED_HOLDERS")
    for name,value in (("MINT_AUTHORITY",mint_authority_active),("FREEZE_AUTHORITY",freeze_authority_active)):
        if type(value) is not bool:
            unknown.append(name)
        elif value:
            risks.append(name+"_ACTIVE")
    if route_verified is not True:
        unknown.append("EXIT_ROUTE")
    return dict(status="RISK_BLOCK" if risks else "UNKNOWN_BLOCK" if unknown else "NO_FLAG_OBSERVED",risks=risks,unknown=unknown,orders=[])


def liquidity_watch(previous, current, *, as_of, max_gap=120):
    """Same-pool receipt-time comparison; USD decline is not proof of withdrawal."""
    unknown=dict(status="UNKNOWN",orders=[],withdrawal_verified=False)
    try:
        for key in ("mint","pair","source"):
            if not isinstance(previous[key],str) or not previous[key] or previous[key]!=current[key]:
                return unknown
        if previous["source"]!="dexscreener":
            return unknown
        a,b,t,u=(previous["liquidity_usd"],current["liquidity_usd"],previous["received_at"],current["received_at"])
        if not all(type(x) in (int,float) and math.isfinite(x) for x in (a,b,t,u,as_of)):
            return unknown
        if not (a>0 and b>=0 and 0<t<u<=as_of and u-t<=max_gap and as_of-u<=60):
            return unknown
    except (KeyError,TypeError,ValueError):
        return unknown
    drop=100*(a-b)/a
    return dict(status="LIQUIDITY_DROP_ALERT" if drop>=30 else "LIQUIDITY_WATCH" if drop>=15 else "NO_DROP_ALERT",
                drop_pct=drop,orders=[],withdrawal_verified=False,scope="OBSERVATION_ONLY")

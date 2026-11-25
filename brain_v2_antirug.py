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

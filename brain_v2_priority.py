"""Read-only PAPER priority planner. Never executes orders."""
import math
PRIORITY={"EMERGENCY":0,"PROFIT_LOCK":1,"STOP":2,"WHALE":3,"RADAR":4,"ESCALERA":5}
def plan(intents):
    seen=set()
    rows=[]
    for i in intents:
        key=i["id"]
        kind=i["kind"]
        if not isinstance(key,str) or not key or key in seen or kind not in PRIORITY:
            raise ValueError("invalid or duplicate intent")
        seen.add(key)
        exit_intent=PRIORITY[kind]<=2
        verified=i.get("route_verified") is True and i.get("fresh_quote") is True
        rows.append(dict(id=key,kind=kind,priority=PRIORITY[kind],status=("PAPER_EXIT_CANDIDATE" if verified else "EXIT_UNVERIFIED") if exit_intent else ("WATCH_ONLY" if verified else "HOLD")))
    rows.sort(key=lambda r:(r["priority"],r["id"]))
    if any(r["priority"]<=2 for r in rows):
        for r in rows:
            if r["priority"]>2: r["status"]="DEFERRED_EXIT_PENDING"
    return dict(scope="PAPER_SHADOW_ONLY",queue=rows,orders=[])
def estimated_cost(notional_eur,fee_bps,slippage_bps,priority_fee_eur):
    values=(notional_eur,fee_bps,slippage_bps,priority_fee_eur)
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values) or notional_eur<=0:
        raise ValueError("invalid cost evidence")
    return notional_eur*(fee_bps+slippage_bps)/10000+priority_fee_eur

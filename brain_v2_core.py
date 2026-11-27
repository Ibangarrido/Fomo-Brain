"""Shadow-only coordinator. Never writes a portfolio or submits orders."""
from copy import deepcopy
import brain_v2_sentinel as sentinel
import brain_v2_guardian as guardian
import brain_v2_radar as radar
import brain_v2_memory as memory
import brain_v2_whale as whale
import brain_v2_social as social
import brain_v2_simulator as simulator
import brain_v2_predictor as predictor
from brain_v2_antirug import liquidity_watch
from brain_v2_profit_experiment import staircase_watch

def cycle(*, state, previous, now, candidates, journal, fills=()):
    journal=deepcopy(journal)
    errors=[]
    def safe(name, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            errors.append(dict(module=name,error=type(exc).__name__))
            return None
    health=safe("sentinel",sentinel.audit,state,previous,now)
    healthy=health is not None and not health["issues"]
    rows=[]
    for c in candidates:
        try:
            mint=c["mint"]
            t=now.timestamp()
            risk=safe("guardian",guardian.assess,**c["risk"])
            signal=safe("radar",radar.assess,**c["radar"])
            w=safe("whale",whale.classify,c.get("swaps",[]),wallet=c.get("wallet"),mint=mint,now=t)
            s=safe("social",social.assess,c.get("posts",[]),mint=mint,now=t)
            p=safe("predictor",predictor.describe,c.get("features",[]),c.get("analogs",[]),as_of=t)
            history=c.get("market_history",[])
            if any(x.get("mint")!=mint for x in history):
                raise ValueError("history mint mismatch")
            stairs=safe("staircase",staircase_watch,history,as_of=t)
            liquidity=safe("liquidity",liquidity_watch,history[-2],history[-1],as_of=t) if len(history)>=2 else None
            remembered=safe("risk_memory",memory.risk_memory,journal,chain=c["chain"],mint=mint,as_of=t)
            alerts=[x["status"] for x in (stairs,liquidity) if x and x["status"] in ("REPEAT_CRASH_ALERT","LIQUIDITY_DROP_ALERT")]
            blocked=bool(alerts) or remembered is None or remembered["status"]=="RISK_REVIEW" or (w and w.get("label")=="DISTRIBUTION_WATCH")
            decision="WATCH_ONLY" if healthy and risk=="MONITOR" and signal=="EARLY_WATCH" and not blocked else "HOLD"
            reason=f"health={healthy};risk={risk};radar={signal}"
            key=safe("memory",memory.record,journal,mint=mint,chain=c["chain"],timestamp=t,
                     price=c["risk"]["price"],decision=decision,reason=reason,
                     features=dict(radar=signal,risk=risk,whale=w,social=s,predictor=p,staircase=stairs,liquidity=liquidity,risk_history=remembered["status"] if remembered else "UNKNOWN",risk_alert=alerts[0] if alerts else None,pair=history[-1].get("pair") if history else None),strategy="core-shadow-v1")
            rows.append(dict(mint=mint,decision=decision if key else "HOLD",reason=reason,memory_id=key,risk_alerts=alerts,risk_block=bool(blocked)))
        except Exception as exc:
            errors.append(dict(module="candidate",error=type(exc).__name__))
            rows.append(dict(decision="HOLD",reason="INVALID_CANDIDATE"))
    simulation=safe("simulator",simulator.replay,fills)
    return dict(scope="PAPER_SHADOW_ONLY",health=health,decisions=rows,journal=journal,
                simulation=simulation,errors=errors,orders=[])

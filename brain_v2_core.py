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
            decision="WATCH_ONLY" if healthy and risk=="MONITOR" and signal=="EARLY_WATCH" else "HOLD"
            reason=f"health={healthy};risk={risk};radar={signal}"
            key=safe("memory",memory.record,journal,mint=mint,chain=c["chain"],timestamp=t,
                     price=c["risk"]["price"],decision=decision,reason=reason,
                     features=dict(radar=signal,risk=risk,whale=w,social=s,predictor=p),strategy="core-shadow-v1")
            rows.append(dict(mint=mint,decision=decision if key else "HOLD",reason=reason,memory_id=key))
        except Exception as exc:
            errors.append(dict(module="candidate",error=type(exc).__name__))
            rows.append(dict(decision="HOLD",reason="INVALID_CANDIDATE"))
    simulation=safe("simulator",simulator.replay,fills)
    return dict(scope="PAPER_SHADOW_ONLY",health=health,decisions=rows,journal=journal,
                simulation=simulation,errors=errors,orders=[])

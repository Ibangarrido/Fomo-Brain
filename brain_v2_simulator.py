"""Offline replay of supplied hypothetical executable fills; no trading."""
import math

def replay(events, *, initial=100, fee_bps=20, slippage_bps=20):
    def valid(x):
        return type(x) in (int,float) and math.isfinite(x)
    if not all(valid(x) for x in (initial,fee_bps,slippage_bps)) or initial <= 0 or min(fee_bps,slippage_bps)<0 or fee_bps+slippage_bps>=10000:
        raise ValueError("invalid configuration")
    cost=(fee_bps+slippage_bps)/10000
    cash=float(initial)
    positions={}
    seen=set()
    last=-math.inf
    peak=cash
    drawdown=0
    closed=[]
    for e in events:
        t,p=e["timestamp"],e["price"]
        key,mint=e["id"],e["mint"]
        if not valid(t) or t<last or not valid(p) or p<=0 or not key or key in seen or not mint:
            raise ValueError("invalid or duplicate event")
        if e.get("executable") is not True:
            raise ValueError("unverified hypothetical fill")
        if not valid(e.get("signal_at")) or e["signal_at"]>=t:
            raise ValueError("fill must follow signal")
        seen.add(key)
        last=t
        if e["side"]=="buy":
            amount=e["eur"]
            if not valid(amount) or not 0<amount<=10 or amount>cash or mint in positions or len(positions)>=3:
                raise ValueError("exposure limit")
            cash-=amount
            positions[mint]=(amount*(1-cost)/p,amount,p)
        elif e["side"]=="sell":
            if mint not in positions:
                raise ValueError("no position")
            qty,spent,_=positions.pop(mint)
            proceeds=qty*p*(1-cost)
            cash+=proceeds
            closed.append(proceeds-spent)
        else:
            raise ValueError("unknown side")
        if not positions:
            peak=max(peak,cash)
            drawdown=max(drawdown,(peak-cash)/peak)
    return dict(cash=cash,open_count=len(positions),closed_count=len(closed),
                realized_pnl=math.fsum(closed),net_return_pct=100*(cash/initial-1) if not positions else None,
                flat_checkpoint_drawdown_pct=100*drawdown,
                wins=sum(x>0 for x in closed),losses=sum(x<0 for x in closed))

"""Public read-only polling; receipt time is not exchange quote time."""
import json
import math
import re
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE="https://api.dexscreener.com/token-pairs/v1/solana/"
def fetch(mint, *, opener=urlopen, clock=time.time, sleep=time.sleep):
    if not isinstance(mint,str) or not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}",mint):
        raise ValueError("invalid mint")
    for attempt in range(3):
        try:
            with opener(Request(BASE+mint, headers={"Accept":"application/json","User-Agent":"FomoBrain-Paper/2.0"}),timeout=10) as response:
                raw=response.read(2_000_001)
            break
        except (HTTPError, URLError, TimeoutError, ConnectionError) as exc:
            if isinstance(exc, HTTPError) and exc.code not in (408, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            sleep(2 ** attempt)
    if len(raw)>2_000_000:
        raise ValueError("oversized response")
    rows=json.loads(raw)
    if not isinstance(rows,list):
        raise ValueError("unexpected response")
    result=[]
    for row in rows:
        if row.get("chainId")!="solana" or row.get("baseToken",{}).get("address")!=mint:
            continue
        try:
            price=float(row["priceUsd"])
            liquidity=float(row["liquidity"]["usd"])
            if not all(math.isfinite(x) for x in (price,liquidity)) or price<=0 or liquidity<0:
                continue
            pair=row["pairAddress"]
            if not isinstance(pair,str) or not pair:
                continue
        except (KeyError,TypeError,ValueError):
            continue
        result.append(dict(mint=mint,pair=pair,price_usd=price,liquidity_usd=liquidity,
            received_at=clock(),quote_timestamp=None,route_verified=False,source="dexscreener",
            status="OBSERVATION_ONLY"))
    return sorted(result,key=lambda r:(-r["liquidity_usd"],r["pair"]))

def poll(mints, *, fetcher=fetch, rounds=1, interval=30, sleep=time.sleep):
    """Bounded polling; at most ten distinct mints, no orders or ledger writes."""
    mints=list(dict.fromkeys(mints))
    if not 1<=len(mints)<=10 or type(rounds) is not int or not 1<=rounds<=120 or not 30<=interval<=300:
        raise ValueError("invalid polling budget")
    for i in range(rounds):
        batch=[]
        for mint in mints:
            try:
                rows=fetcher(mint)
                batch.append(dict(mint=mint,status="OK" if rows else "NO_DATA",observations=rows))
            except Exception as exc:
                batch.append(dict(mint=mint,status="SOURCE_ERROR",error=type(exc).__name__,http_status=exc.code if isinstance(exc,HTTPError) else None,observations=[]))
        yield batch
        if i+1<rounds:
            sleep(interval if all(r["status"]!="SOURCE_ERROR" for r in batch) else min(300,interval*2))

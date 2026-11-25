import json, math, re, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

def request(url, payload=None):
    req=Request(url,data=None if payload is None else json.dumps(payload).encode(),headers={"Accept":"application/json","Content-Type":"application/json","User-Agent":"FomoBrain-Paper/2.0"})
    with urlopen(req,timeout=10) as r:
        raw=r.read(2000001)
        if len(raw)>2000000: raise ValueError("response too large")
        return json.loads(raw)

def bridge(mint, *, transport=request, clock=time.time):
    if not isinstance(mint,str) or not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}",mint): raise ValueError("invalid mint")
    sources={}
    def attempt(name,fn):
        try:
            data=fn()
            sources[name]={"status":"OK" if data is not None else "NO_DATA","data":data,"received_at":clock()}
        except Exception as exc:
            sources[name]={"status":"SOURCE_ERROR","error_type":type(exc).__name__,"http_status":exc.code if isinstance(exc,HTTPError) else None,"received_at":clock()}
    def rpc(method,config):
        r=transport("https://api.mainnet-beta.solana.com",{"jsonrpc":"2.0","id":1,"method":method,"params":[mint,config]})
        if r.get("error") or r.get("id")!=1: raise ValueError("RPC error")
        return r["result"]
    def account():
        r=rpc("getAccountInfo",{"encoding":"jsonParsed","commitment":"finalized"})
        if r["value"] is None: return None
        p=r["value"]["data"]["parsed"]
        if p["type"]!="mint": raise ValueError("not mint")
        i=p["info"]
        return dict(slot=r["context"]["slot"],mint_authority_active=i["mintAuthority"] is not None,freeze_authority_active=i["freezeAuthority"] is not None,supply=i["supply"],decimals=i["decimals"],program=r["value"]["owner"])
    def number(x,positive=False):
        f=float(x)
        if not math.isfinite(f) or f<0 or (positive and f==0): raise ValueError("invalid number")
        return f
    def dex():
        rows=transport("https://api.dexscreener.com/token-pairs/v1/solana/"+mint)
        if not isinstance(rows,list): raise ValueError("invalid response")
        out=[]
        for p in rows:
            if p.get("chainId")!="solana" or p.get("baseToken",{}).get("address")!=mint: continue
            try: out.append(dict(pool=p["pairAddress"],price_usd=number(p["priceUsd"],True),liquidity_usd=number(p["liquidity"]["usd"]),volume_5m=p.get("volume",{}).get("m5"),transactions_5m=p.get("txns",{}).get("m5")))
            except (ValueError,KeyError,TypeError): continue
        if rows and not out: raise ValueError("no valid matching pairs")
        return max(out,key=lambda p:p["liquidity_usd"]) if out else None
    def gecko():
        r=transport("https://api.geckoterminal.com/api/v2/networks/solana/tokens/"+mint)
        d=r["data"]
        if d is None: return None
        a=d["attributes"]
        if a["address"]!=mint: raise ValueError("wrong mint")
        return dict(price_usd=number(a["price_usd"],True))
    attempt("solana_rpc",account)
    attempt("dexscreener",dex)
    attempt("geckoterminal",gecko)
    return dict(mint=mint,sources=sources,scope="PAPER_OBSERVATION_ONLY",quote_timestamp=None,route_verified=False,decision="HOLD",orders=[])

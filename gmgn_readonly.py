"""GMGN market-data preflight. No wallet, signing, swaps or paper fills."""
import json
import os
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HOST = "https://openapi.gmgn.ai"
M4 = "HciAVS1urBtboqhLe59HWiMeeN2McEd6y8h4HGkrpump"
ENDPOINTS = {
    "info": "/v1/token/info",
    "security": "/v1/token/security",
    "pool": "/v1/token/pool_info",
    "candles": "/v1/market/token_kline",
    "ranking": "/v1/market/rank",
}
MAX_BYTES = 2_000_000
DEMO_HOST = "https://papi.gmgn.ai"  # Diagnostic-only, not used by production queries


def query(kind, api_key, opener=urllib.request.urlopen, host=HOST):
    # Closed endpoint allow-list: callers cannot request trade/account routes.
    path = ENDPOINTS[kind]
    if host not in (HOST, DEMO_HOST):
        raise ValueError("Unapproved GMGN host")
    params = {"chain": "sol", "timestamp": int(time.time()), "client_id": str(uuid.uuid4())}
    if kind == "ranking":
        params.update(interval="5m", limit=20, order_by="volume", direction="desc")
    else:
        params["address"] = M4
    if kind == "candles":
        params.update(resolution="1m", **{"from": int(time.time()) - 3600, "to": int(time.time())})
    request = urllib.request.Request(host + path + "?" + urllib.parse.urlencode(params),
        headers={"X-APIKEY": api_key, "Accept": "application/json"}, method="GET")
    with opener(request, timeout=8) as response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Oversized response")
        envelope = json.loads(raw)
        if response.status != 200 or not isinstance(envelope, dict) or type(envelope.get("code")) is not int or envelope["code"] != 0:
            raise ValueError("Provider rejected request")
        data = envelope.get("data")
        if not isinstance(data, (dict, list)) or not data:
            raise ValueError("Missing market data")
        return data


def schema_summary(data):
    """Schema evidence only. Never retain response values or echoed credentials."""
    keys = sorted(k for k in data if isinstance(k, str) and k.isidentifier() and len(k) <= 60)[:40] if isinstance(data, dict) else []
    return {"type": type(data).__name__, "top_level_keys": keys,
            "top_level_items": len(data), "schema_validated_for_trading": False}


def preflight(api_key=None, fetch=query, pause=time.sleep):
    api_key = os.getenv("GMGN_API_KEY", "").strip() if api_key is None else api_key
    report = {"version": "gmgn-readonly-r1", "received_at": datetime.now(timezone.utc).isoformat(),
        "source": "GMGN official Agent OpenAPI", "mode": "READ_ONLY_PREFLIGHT",
        "execution_enabled": False, "paper_entries_enabled": False,
        "status": "MISSING_API_KEY", "endpoints": {},
        "market_freshness": "UNVERIFIED", "net_exit_value": None}
    if not api_key:
        return report
    for index, kind in enumerate(ENDPOINTS):
        if index:
            pause(1)
        try:
            report["endpoints"][kind] = dict(status="RESPONSE_RECEIVED", **schema_summary(fetch(kind, api_key)))
        except urllib.error.HTTPError as exc:
            report["endpoints"][kind] = {"status": "HTTP_ERROR", "http_status": exc.code}
            # Do not retry credential/rate-limit failures or expose provider bodies.
            if exc.code in (401, 403, 429):
                break
        except Exception:
            report["endpoints"][kind] = {"status": "UNAVAILABLE"}
    successes = sum(item["status"] == "RESPONSE_RECEIVED" for item in report["endpoints"].values())
    report["status"] = "AWAITING_SCHEMA_VALIDATION" if successes == len(ENDPOINTS) else "PARTIAL_OR_UNAVAILABLE"
    return report


def main():
    report = preflight()
    with open("gmgn_preflight.json.tmp", "w") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    os.replace("gmgn_preflight.json.tmp", "gmgn_preflight.json")
    print("GMGN PREFLIGHT " + json.dumps(report, allow_nan=False))


if __name__ == "__main__":
    main()

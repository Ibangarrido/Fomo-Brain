"""Prospective PAPER laboratory; never changes historical V10 or whale books."""
from datetime import datetime, timezone
import json
import math
import time
import urllib.parse
import urllib.request

NETWORKS = {"solana": "solana", "bsc": "bsc", "ethereum": "eth",
            "base": "base", "robinhood": "robinhood"}
MAX_REQUESTS_PER_MINUTE = 6
REQUEST_TIMES = []
CYCLE_CACHE = {}
CYCLE_DECISIONS = []


def same_address(a, b, chain):
    return str(a) == str(b) if chain == "solana" else str(a).lower() == str(b).lower()


def request_json(url):
    now = time.monotonic()
    REQUEST_TIMES[:] = [t for t in REQUEST_TIMES if now - t < 60]
    if len(REQUEST_TIMES) >= MAX_REQUESTS_PER_MINUTE:
        raise ValueError("presupuesto OHLCV agotado; cobertura limitada")
    REQUEST_TIMES.append(now)
    req = urllib.request.Request(url, headers={"User-Agent": "FOMO-Brain/Candle-Lab-r1"})
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode())


def validate_pool(payload, token, network):
    data = payload.get("data") or {}
    attrs = data.get("attributes") or {}
    pool = str(attrs.get("address") or "")
    if data.get("id") != network + "_" + pool or not same_address(pool, token["pair"], token["chain"]):
        raise ValueError("pool OHLCV no coincide con el par exacto")
    rel = data.get("relationships") or {}
    wanted = network + "_" + token["address"]
    ids = [((rel.get(side) or {}).get("data") or {}).get("id", "")
           for side in ("base_token", "quote_token")]
    if not any(same_address(i, wanted, token["chain"]) for i in ids):
        raise ValueError("contrato OHLCV no coincide con el token")
    return pool


def evaluate_rows(payload, now):
    """Five consecutive completed minute bars; no forward data or empty intervals."""
    rows = {}
    for row in ((payload.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []:
        if not isinstance(row, list) or len(row) < 6:
            continue
        try:
            ts, o, h, low, c, volume = map(float, row[:6])
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(v) for v in (ts, o, h, low, c, volume)):
            continue
        if ts != int(ts) or int(ts) % 60 or ts + 60 > now:
            continue
        if not (0 < low <= min(o, c) <= max(o, c) <= h and volume >= 0):
            continue
        bar = [ts, o, h, low, c, volume]
        if ts in rows and rows[ts] != bar:
            return {"status": "SIN DATOS", "reason": "velas duplicadas contradictorias"}
        rows[ts] = bar
    bars = sorted(rows.values(), key=lambda r: r[0])[-5:]
    if len(bars) < 5:
        return {"status": "SIN DATOS", "reason": "faltan cinco velas cerradas"}
    if now - (bars[-1][0] + 60) > 90:
        return {"status": "SIN DATOS", "reason": "ultima vela cerrada antigua"}
    if any(b[0] - a[0] != 60 for a, b in zip(bars, bars[1:])):
        return {"status": "SIN DATOS", "reason": "huecos entre velas 1m"}
    a, b = bars[-2:]
    recent = (a[5] + b[5]) / 2
    previous = sum(r[5] for r in bars[:3]) / 3
    wick = (b[2] - max(b[1], b[4])) / (b[2] - b[3]) if b[2] > b[3] else 0
    reason = (
        "dos velas recientes no mantienen cierres crecientes"
        if not (a[4] > a[1] and b[4] > b[1] and b[4] > a[4]) else
        "volumen reciente no supera media previa"
        if previous <= 0 or recent < previous * 1.10 or a[5] <= 0 or b[5] <= 0 else
        "rechazo superior de la ultima vela >40%" if wick > 0.40 else None)
    return {"status": "RECHAZA" if reason else "PASA", "reason": reason,
            "bars": bars, "last_closed_at": datetime.fromtimestamp(b[0] + 60, timezone.utc).isoformat(),
            "recent_volume_mean_usd": recent, "previous_volume_mean_usd": previous,
            "upper_wick_fraction": wick, "policy": "candle-r1"}


def context(token, fetcher=request_json, now=None):
    network = NETWORKS.get(token["chain"])
    if not network:
        return {"status": "SIN DATOS", "reason": "cadena OHLCV no soportada"}
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    key = (token["chain"], token["address"], token["pair"])
    if key in CYCLE_CACHE:
        return CYCLE_CACHE[key]
    try:
        root = "https://api.geckoterminal.com/api/v2/networks/" + network + "/pools/"
        pool_url = root + urllib.parse.quote(token["pair"], safe="")
        validate_pool(fetcher(pool_url), token, network)
        params = urllib.parse.urlencode({"aggregate": 1, "limit": 8, "currency": "usd",
                                         "token": token["address"]})
        result = evaluate_rows(fetcher(pool_url + "/ohlcv/minute?" + params), now)
        result.update(source="GeckoTerminal", chain=token["chain"],
                      address=token["address"], pair=token["pair"])
    except Exception as exc:
        result = {"status": "SIN DATOS", "reason": str(exc)}
    CYCLE_CACHE[key] = result
    return result


def guard(filtered, mode=None):
    def check(token):
        result = context(token)
        CYCLE_DECISIONS.append({"at": datetime.now(timezone.utc).isoformat(),
                                "mode": mode, "filtered": filtered,
                                "chain": token["chain"] if "chain" in token else None,
                                "address": token.get("address"), "context": result})
        token["candle_context"] = result
        token["entry_policy_suffix"] = "+candle-r1" if filtered else "+lab-control-r1"
        print("LAB OHLCV " + token["chain"] + ":" + token["address"]
              + " | brazo=" + ("VELAS" if filtered else "CONTROL")
              + " | " + json.dumps(result, ensure_ascii=False))
        if filtered and result["status"] != "PASA":
            return "LAB candle-r1: " + str(result.get("reason") or result["status"])
        return None
    return check


def run(ranking, simulator):
    CYCLE_CACHE.clear()
    CYCLE_DECISIONS.clear()
    print("LAB VELAS r1: cuatro carteras ficticias separadas de 100 EUR; NO sumar ni atribuir a V10 historicas.")
    # Control may buy without OHLCV; filtered arm rejects missing data.
    # Coverage is recorded to distinguish a price filter from an API limitation.
    for mode in ("early", "impulse"):
        for filtered in (False, True):
            arm = "velas" if filtered else "control"
            simulator(ranking, "fomo_lab_" + mode + "_" + arm + "_r1.json",
                      "LAB " + mode.upper() + " " + arm.upper() + " r1",
                      confirm=True, entry_mode=mode, entry_guard=guard(filtered, mode))

    try:
        with open("fomo_lab_candle_audit_r1.json") as handle:
            audit = json.load(handle)
    except FileNotFoundError:
        audit = []
    audit = (audit + CYCLE_DECISIONS)[-1000:]
    with open("fomo_lab_candle_audit_r1.json.tmp", "w") as handle:
        json.dump(audit, handle, indent=2)
    import os
    os.replace("fomo_lab_candle_audit_r1.json.tmp", "fomo_lab_candle_audit_r1.json")
    print("LAB COBERTURA OHLCV " + json.dumps({
        status: sum(d["context"]["status"] == status for d in CYCLE_DECISIONS)
        for status in ("PASA", "RECHAZA", "SIN DATOS")}))

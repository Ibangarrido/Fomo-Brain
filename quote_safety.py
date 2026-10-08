"""Read-only checks for virtual prices and Solana transfer fees."""
import math
import hashlib
import json
import time
import urllib.parse
from datetime import datetime, timezone

FEE_CACHE = {}
NETWORKS = {"solana": "solana", "bsc": "bsc", "ethereum": "eth", "base": "base", "robinhood": "robinhood"}


def extreme(price, previous):
    # Data-quality hypothesis, not an optimized trading threshold or a stop.
    return previous > 0 and (price / previous <= .70 or price / previous >= 1.50)


def record_market_observation(pos, price, pair, now=None):
    """Receipt time is NOT trade time; repeated snapshots do not prove staleness."""
    now = now or datetime.now(timezone.utc)
    receipt = now.isoformat()
    market = {key: pair.get(key) for key in (
        "pairAddress", "priceUsd", "liquidity", "txns", "volume", "priceChange")}
    fingerprint = hashlib.sha256(json.dumps(market, sort_keys=True).encode()).hexdigest()
    audit = pos.setdefault("quote_audit", {})
    if audit.get("pair") != pair["pairAddress"] or audit.get("fingerprint") != fingerprint:
        audit["snapshot_unchanged_since"] = receipt
    if audit.get("pair") != pair["pairAddress"] or audit.get("price") != price:
        audit["price_unchanged_since"] = receipt
    audit.update(version="quote-r2", pair=pair["pairAddress"], price=price,
                 fingerprint=fingerprint, received_at=receipt,
                 source_timestamp=None, market_data_age_seconds=None,
                 freshness="DESCONOCIDA: API sin timestamp del precio")
    for field in ("snapshot", "price"):
        audit[field + "_unchanged_seconds"] = max(
            0, (now - datetime.fromisoformat(audit[field + "_unchanged_since"])).total_seconds())
    row = {"received_at": receipt, "pair": pair["pairAddress"], "price": price,
           "liquidity": (pair.get("liquidity") or {}).get("usd"),
           "source_timestamp": None, "market_data_age_seconds": None,
           "snapshot_unchanged_seconds": audit["snapshot_unchanged_seconds"],
           "price_unchanged_seconds": audit["price_unchanged_seconds"]}
    pos.setdefault("quote_history", []).append(row)
    pos["quote_history"] = pos["quote_history"][-360:]
    return row


def corroborate(pos, price, fetch):
    network = NETWORKS.get(pos["chain"])
    if not network:
        raise ValueError("SIN COBERTURA: cadena de contraste no soportada")
    url = "https://api.geckoterminal.com/api/v2/networks/" + network + "/pools/" + urllib.parse.quote(pos["pair"], safe="")
    payload = fetch(url)
    from candle_lab import validate_pool, same_address
    validate_pool(payload, pos, network)
    data = payload["data"]
    base = data["relationships"]["base_token"]["data"]["id"]
    if not same_address(base, network + "_" + pos["address"], pos["chain"]):
        raise ValueError("contraste: token no es base del pool")
    second = float(data["attributes"].get("base_token_price_usd"))
    if not math.isfinite(second) or second <= 0:
        raise ValueError("contraste: precio ausente o invalido")
    evidence = {"version": "quote-r2", "primary_price": price, "secondary_price": second,
                "secondary_source": "GeckoTerminal", "pool": pos["pair"],
                "chain": pos["chain"], "address": pos["address"],
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "source_timestamp": None, "market_data_age_seconds": None,
                "execution_verified": False,
                "status": "COINCIDE" if abs(price / second - 1) <= .20 else "DISCREPANCIA"}
    return evidence


def entry_fees(token, fetch):
    if token["chain"] != "solana":
        return {"status": "SIN COBERTURA", "chain": token["chain"]}, None
    address = token["address"]
    cached = FEE_CACHE.get(address)
    if cached and time.monotonic() - cached[0] < 300:
        return cached[1], cached[2]
    try:
        url = "https://api.gopluslabs.io/api/v1/solana/token_security?contract_addresses=" + urllib.parse.quote(address, safe="")
        payload = fetch(url)
        if payload.get("code") != 1:
            raise ValueError("respuesta GoPlus no valida")
        report = payload["result"][address]
        mutable = report["transfer_fee_upgradable"]["status"]
        fee = report["transfer_fee"]
        absence = None
        if fee == {} and mutable == "0":
            # Empty GoPlus configuration is not itself proof of zero fees.
            # Require an exact-mint second report with an explicit absent extension.
            absence = corroborate_absent_fee(address, fetch)
            rate = 0.0
        else:
            rate = float(fee["current_fee_rate"]["fee_rate"])
        scheduled = fee.get("scheduled_fee_rate", [])
        if not isinstance(scheduled, list):
            raise ValueError("comisiones programadas invalidas")
        future_fee = False
        for item in scheduled:
            future_rate = float(item["fee_rate"])
            if not math.isfinite(future_rate) or future_rate < 0:
                raise ValueError("comision programada invalida")
            future_fee = future_fee or future_rate > 0
        if not math.isfinite(rate) or not 0 <= rate <= 1 or mutable not in ("0", "1"):
            raise ValueError("comision o autoridad invalida")
        evidence = {"status": "VERIFICADO", "source": "GoPlus", "address": address,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "transfer_fee_rate": rate, "transfer_fee_mutable": mutable == "1",
                    "version": "fee-r2", "absence_crosscheck": absence,
                    "scheduled_positive_fee": future_fee}
        reason = "comision de transferencia positiva o modificable; costes no modelados" if rate > 0 or mutable == "1" or future_fee else None
    except Exception as exc:
        evidence = {"status": "SIN DATOS", "source": "GoPlus", "address": address, "reason": str(exc)}
        reason = "comision Solana sin verificar"
    if evidence["status"] == "VERIFICADO":
        FEE_CACHE[address] = (time.monotonic(), evidence, reason)
        if len(FEE_CACHE) > 256:
            del FEE_CACHE[next(iter(FEE_CACHE))]
    return evidence, reason


def corroborate_absent_fee(address, fetch):
    url = "https://api.rugcheck.xyz/v1/tokens/" + urllib.parse.quote(address, safe="") + "/report"
    report = fetch(url)
    if report.get("mint") != address or report.get("token", {}).get("isInitialized") is not True:
        raise ValueError("contraste comision: contrato o mint invalido")
    program = report.get("tokenProgram")
    if program == "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb":
        extensions = report.get("token_extensions")
        if not isinstance(extensions, dict) or "transferFeeConfig" not in extensions or extensions["transferFeeConfig"] is not None:
            raise ValueError("contraste comision: extension ausente no confirmada")
    elif program != "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA":
        raise ValueError("contraste comision: programa no reconocido")
    return {"source": "RugCheck", "address": address, "token_program": program,
            "status": "SIN EXTENSION DE COMISION",
            "observed_at": datetime.now(timezone.utc).isoformat()}


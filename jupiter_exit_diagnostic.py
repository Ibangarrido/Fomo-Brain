"""Read-only Solana Jupiter route diagnostics. Never signs or sends transactions."""
import json
import urllib.parse
import urllib.request

HOST = "https://lite-api.jup.ag"
MAX_RESPONSE_BYTES = 200_000


def quote(input_mint, output_mint, amount_raw, opener=urllib.request.urlopen):
    if not all(isinstance(m, str) and 32 <= len(m) <= 44 and m.isalnum() for m in (input_mint, output_mint)):
        raise ValueError("Invalid mint")
    if type(amount_raw) is not int or amount_raw <= 0:
        raise ValueError("Invalid raw amount")
    params = urllib.parse.urlencode({"inputMint": input_mint, "outputMint": output_mint, "amount": amount_raw, "swapMode": "ExactIn"})
    request = urllib.request.Request(HOST + "/swap/v1/quote?" + params, headers={"Accept": "application/json"}, method="GET")
    with opener(request, timeout=8) as response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ValueError("Oversized quote")
        data = json.loads(payload)
    if not isinstance(data, dict) or not str(data.get("outAmount", "")).isdigit() or int(data["outAmount"]) <= 0:
        raise ValueError("No usable exit quote")
    if data.get("inputMint") != input_mint or data.get("outputMint") != output_mint:
        raise ValueError("Mint mismatch")
    return {"status": "INDICATIVE_ONLY", "out_amount_raw": data["outAmount"],
            "price_impact_pct": data.get("priceImpactPct"),
            "route_hops": len(data.get("routePlan", [])),
            "executable_verified": False, "trade_enabled": False}

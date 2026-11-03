"""Public Solana observations for FLOAT; NO trader attribution without proof.

This module never sends transactions, signs messages, opens PAPER positions,
or reads FOMO private/internal endpoints.
"""
import json
import urllib.request

FLOAT_MINT = "Bv1a7cEj5aRnJQhMw4kRQqAFesMSd5LwcDnUzq52BMmr"
PUBLIC_RPC = "https://api.mainnet-beta.solana.com"

def rpc_read(method, params, *, endpoint=PUBLIC_RPC, timeout=12):
    if method not in ("getSignaturesForAddress", "getTransaction"):
        raise ValueError("Read-only RPC method required")
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                          "params": params}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    if "error" in data:
        raise RuntimeError("Solana RPC error: " + str(data["error"]))
    return data.get("result")

def token_signatures(*, limit=20, before=None, endpoint=PUBLIC_RPC):
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("Invalid bounded page size")
    opts = {"limit": limit}
    if before is not None:
        opts["before"] = before
    result = rpc_read("getSignaturesForAddress", [FLOAT_MINT, opts], endpoint=endpoint)
    return result if isinstance(result, list) else []

def transaction(signature, *, endpoint=PUBLIC_RPC):
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError("Missing transaction signature")
    return rpc_read("getTransaction", [signature, {
        "encoding": "jsonParsed", "maxSupportedTransactionVersion": 0
    }], endpoint=endpoint)

def classify_observation(signature, tx, *, verified_wallet=None):
    """A mint transaction is not evidence of a particular trader's trade."""
    if not isinstance(tx, dict) or not isinstance(tx.get("slot"), int):
        return {"signature": signature, "status": "UNVERIFIED_TRANSACTION",
                "trader": None, "paper_entry": False}
    return {"signature": signature, "slot": tx["slot"],
            "block_time": tx.get("blockTime"),
            "status": "PUBLIC_TRANSACTION_UNATTRIBUTED",
            "trader": None, "paper_entry": False,
            "wallet_attribution": "NOT_VERIFIED",
            "note": "Mint address and fee payer do not establish Surgz ownership"}

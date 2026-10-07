"""Read-only quantity quotes and mint metadata. Never builds transactions."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import glob
import json
import threading
import time
import urllib.parse
import urllib.request

from exit_watchdog import wallet_lock

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
VERSION = "route-shadow-r2"


def get_json(url):
    # Separate client/cache from entry and exit watchers; bounded GETs only.
    request = urllib.request.Request(url, headers={"User-Agent": "FOMO-Brain/route-shadow-r1"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode())


def token_supply(mint):
    """Read-only RPC method, not transaction submission; exact validated mint."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "getTokenSupply",
               "params": [mint, {"commitment": "confirmed"}]}
    request = urllib.request.Request("https://api.mainnet-beta.solana.com",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "FOMO-Brain/route-shadow-r2"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode())


def mint_decimals(mint, fetch, supply_reader):
    try:
        metadata = fetch("https://api-v3.raydium.io/mint/ids?" + urllib.parse.urlencode({"mints": mint}))
        matches = [m for m in metadata.get("data") or []
                   if isinstance(m, dict) and m.get("address") == mint]
        if metadata.get("success") is not True or len(matches) != 1:
            raise ValueError("Exact mint metadata unavailable")
        decimals = matches[0].get("decimals")
        raw_quantity(1, decimals)
        return decimals, {"source": "Raydium mint API", "context_slot": None}
    except Exception as exc:
        primary_error = type(exc).__name__ + ": " + str(exc)[:160]
    response = supply_reader(mint)
    result = response.get("result") or {}
    value = result.get("value") or {}
    slot = (result.get("context") or {}).get("slot")
    if (response.get("jsonrpc") != "2.0" or response.get("id") != 1 or response.get("error")
            or type(slot) is not int or slot <= 0
            or not isinstance(value.get("amount"), str) or not value["amount"].isdigit()):
        raise ValueError("Invalid getTokenSupply response; primary=" + primary_error)
    decimals = value.get("decimals")
    raw_quantity(1, decimals)
    return decimals, {"source": "Solana RPC getTokenSupply confirmed", "context_slot": slot,
                      "primary_metadata_error": primary_error}


def raw_quantity(quantity, decimals):
    if type(decimals) is not int or not 0 <= decimals <= 18:
        raise ValueError("Invalid mint decimals")
    value = Decimal(str(quantity))
    if not value.is_finite() or value <= 0:
        raise ValueError("Invalid paper quantity")
    amount = int((value * (10 ** decimals)).to_integral_value(rounding=ROUND_DOWN))
    if not 0 < amount < 2 ** 64:
        raise ValueError("Quantity outside uint64")
    return amount


def quote(position, fetch=get_json, supply_reader=token_supply):
    if position.get("chain") != "solana":
        raise ValueError("Solana only")
    mint = position["address"]
    if not isinstance(mint, str) or not 32 <= len(mint) <= 44 or any(
            c not in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in mint):
        raise ValueError("Invalid mint")
    decimals, metadata_evidence = mint_decimals(mint, fetch, supply_reader)
    amount = raw_quantity(position["quantity"], decimals)
    query = urllib.parse.urlencode({"inputMint": mint, "outputMint": USDC,
                                   "amount": str(amount), "slippageBps": "200", "txVersion": "V0"})
    started = time.monotonic()
    result = fetch("https://transaction-v1.raydium.io/compute/swap-base-in?" + query)
    data = result.get("data") or {}
    if result.get("success") is not True:
        raise ValueError("Provider quote unavailable: " + str(result.get("msg", "unknown"))[:160])
    if (data.get("inputMint") != mint or data.get("outputMint") != USDC
            or str(data.get("inputAmount")) != str(amount) or data.get("swapType") != "BaseIn"
            or data.get("slippageBps") != 200 or not data.get("routePlan")):
        raise ValueError("Quote identity/amount/route mismatch")
    output = int(data["outputAmount"])
    threshold = int(data["otherAmountThreshold"])
    if output <= 0 or not 0 <= threshold <= output:
        raise ValueError("Invalid quote output")
    # USDC has six decimals. Report token units, never equate USDC to EUR.
    return {"status": "QUOTE_ONLY", "provider": "Raydium Trade API",
            "mint_decimals": decimals, "mint_metadata": metadata_evidence,
            "input_amount_raw": str(amount),
            "output_mint": USDC, "expected_out_usdc": output / 1_000_000,
            "threshold_usdc": threshold / 1_000_000, "slippage_bps": 200,
            "price_impact_pct": data.get("priceImpactPct"), "route_plan": data["routePlan"],
            "quote_request_seconds": time.monotonic() - started,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "market_data_age_seconds": None, "network_costs_included": False,
            "execution_verified": False}


def snapshots():
    grouped = {}
    for path in sorted(glob.glob("fomo_paper*.json") + glob.glob("fomo_lab*.json")):
        lock = wallet_lock(path)
        if not lock.acquire(blocking=False):
            print(f"ROUTE SHADOW POSPUESTO {path}: cartera ocupada", flush=True)
            continue
        try:
            with open(path) as handle:
                state = json.load(handle)
            positions = state.get("positions", []) if isinstance(state, dict) else []
            for pos in positions:
                if pos.get("chain") != "solana" or not pos.get("quantity"):
                    continue
                # Same quantity can share one read-only route quote across wallets.
                key = (pos["address"], str(pos["quantity"]))
                item = grouped.setdefault(key, {"chain": "solana", "address": pos["address"],
                                                "quantity": pos["quantity"], "wallets": []})
                item["wallets"].append({"path": path, "opened_at": pos.get("opened_at"),
                                       "dex_mark_at": pos.get("last_quote_at"),
                                       "dex_quote_status": pos.get("quote_status"),
                                       "paper_mark_net": pos.get("mark_net"),
                                       "paper_mark_unit": "existing paper-model units; not USDC"})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"ROUTE SHADOW SNAPSHOT ERROR {path}: {type(exc).__name__}", flush=True)
        finally:
            lock.release()
    return list(grouped.values())


class RouteShadow:
    def __init__(self, duration=900, interval=60, fetch=get_json, read=snapshots, supply_reader=token_supply):
        self.duration, self.interval = duration, interval
        self.fetch, self.read = fetch, read
        self.supply_reader = supply_reader
        self.stop_event = threading.Event()
        self.cursor = 0
        self.thread = threading.Thread(target=self.run, name="paper-route-shadow")

    def start(self):
        self.thread.start()
        print("ROUTE SHADOW r2 INICIO | Solana | read-only GET quotes + RPC mint fallback | max4 cantidades/60s | logs only | sin cambios de saldo", flush=True)

    def stop(self):
        self.stop_event.set()
        self.thread.join()

    def tick(self):
        items = self.read()
        if not items:
            print("ROUTE SHADOW COBERTURA | sin posiciones Solana disponibles", flush=True)
            return
        count = min(4, len(items))
        print(f"ROUTE SHADOW COBERTURA | cantidades={len(items)} | consultadas_max={count} | otras cadenas no cubiertas", flush=True)
        for offset in range(count):
            if self.stop_event.is_set():
                break
            item = items[(self.cursor + offset) % len(items)]
            evidence = {"version": VERSION, "snapshot_at": datetime.now(timezone.utc).isoformat(), **item}
            started = time.monotonic()
            try:
                evidence.update(quote(item, self.fetch, self.supply_reader))
            except Exception as exc:
                evidence.update(status="UNAVAILABLE", error=type(exc).__name__ + ": " + str(exc)[:240],
                                execution_verified=False)
            evidence["total_request_seconds"] = time.monotonic() - started
            print("ROUTE SHADOW " + json.dumps(evidence, ensure_ascii=False, allow_nan=False), flush=True)
        self.cursor = (self.cursor + count) % len(items)

    def run(self):
        started = time.monotonic()
        while not self.stop_event.is_set() and time.monotonic() - started < self.duration:
            try:
                self.tick()
            except Exception as exc:
                print(f"ROUTE SHADOW ERROR {type(exc).__name__}: {exc}", flush=True)
            self.stop_event.wait(min(self.interval, max(0, self.duration - (time.monotonic() - started))))

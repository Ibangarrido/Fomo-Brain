"""Read-only quantity quotes and mint metadata. Never builds transactions."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import glob
import json
import os
import threading
import time
import urllib.parse
import urllib.request
import urllib.error

from exit_watchdog import wallet_lock

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
VERSION = "route-shadow-r3"
AUDIT_FILE = "fomo_quote_audit.json"


def fee_evidence(data):
    """Provider-declared fees only; missing fields never mean zero cost."""
    fields = ("signatureFeeLamports", "prioritizationFeeLamports", "rentFeeLamports")
    amounts = {key: data.get(key) if type(data.get(key)) is int
               and data[key] >= 0 else None for key in fields}
    return {"provider_network_fee_lamports": amounts,
            "missing_network_fee_fields": [key for key, value in amounts.items() if value is None],
            "provider_fee_bps": data.get("feeBps") if type(data.get("feeBps")) is int
            and data["feeBps"] >= 0 else None,
            "cost_status": "PROVIDER_ESTIMATE_ONLY" if all(v is not None for v in amounts.values())
            else "NETWORK_COST_UNKNOWN",
            "net_liquidation_value_usdc": None,
            "execution_verified": False}


class QuoteAudit:
    """Bounded evidence for this session only, separate from every paper wallet."""
    def __init__(self, path=AUDIT_FILE):
        self.path = path
        self.state = {"version": "quote-audit-r1", "run_id": os.getenv("GITHUB_RUN_ID"),
                      "started_at": datetime.now(timezone.utc).isoformat(),
                      "execution_verified": False, "records": [], "dropped_records": 0}

    def save(self, kind=None, record=None):
        if record is not None:
            self.state["records"].append({"kind": kind, **record})
            excess = max(0, len(self.state["records"]) - 300)
            if excess:
                del self.state["records"][:excess]
                self.state["dropped_records"] += excess
        try:
            temporary = self.path + ".tmp"
            with open(temporary, "w") as handle:
                json.dump(self.state, handle, ensure_ascii=False, allow_nan=False)
            os.replace(temporary, self.path)
        except (OSError, ValueError, TypeError) as exc:
            print(f"QUOTE AUDIT WRITE ERROR {type(exc).__name__}", flush=True)


class ProviderHTTPError(ValueError):
    """Bounded public provider diagnostics; never retain the response or URL."""
    def __init__(self, status, details):
        super().__init__(f"Provider HTTP {status}")
        self.http_status = status
        self.provider_error = details


def http_diagnostics(exc):
    if isinstance(exc, ProviderHTTPError):
        return {"http_status": exc.http_status, "provider_error": exc.provider_error}
    return {}


def get_json(url):
    # Separate client/cache from entry and exit watchers; bounded GETs only.
    request = urllib.request.Request(url, headers={"User-Agent": "FOMO-Brain/route-shadow-r1"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        details = {}
        try:
            body = exc.read(4097)
            data = json.loads(body.decode()) if len(body) <= 4096 else None
            if isinstance(data, dict):
                for key in ("error", "errorCode", "errorMessage", "msg"):
                    value = data.get(key)
                    if isinstance(value, str):
                        details[key] = "".join(c for c in value[:240] if c.isprintable())
                    elif type(value) is int:
                        details[key] = str(value)[:40]
        except (OSError, ValueError, UnicodeError):
            pass
        finally:
            exc.close()
        raise ProviderHTTPError(exc.code, details) from None


def position_valuations(item, observation):
    """Independent quote marks per snapshot position, never portfolio equity."""
    available = observation.get("status") == "QUOTE_ONLY"
    return [{"wallet": wallet["path"], "chain": item["chain"],
             "address": item["address"], "opened_at": wallet.get("opened_at"),
             "quantity": item["quantity"], "input_amount_raw": observation.get("input_amount_raw"),
             "snapshot_at": observation["snapshot_at"],
             "quote_received_at": observation.get("received_at"),
             "status": "QUOTE_ONLY" if available else "UNAVAILABLE",
             "quoted_value_usdc": observation.get("expected_out_usdc") if available else None,
             "quoted_threshold_usdc": observation.get("threshold_usdc") if available else None,
             "net_liquidation_value_usdc": None, "market_data_age_seconds": None,
             "network_cost_usdc": None, "realized_slippage_usdc": None,
             "fx_applied": False, "execution_verified": False,
             "fee_evidence": observation.get("fee_evidence"),
             "paper_mark_at": wallet.get("dex_mark_at"),
             "paper_quote_status": wallet.get("dex_quote_status")}
            for wallet in item.get("wallets", [])]


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


def raydium_uint64(value):
    """Accept provider integer units without coercion, truncation or overflow."""
    if type(value) is int:
        amount = value
    elif isinstance(value, str) and value.isascii() and value.isdigit():
        amount = int(value)
    else:
        raise ValueError("Invalid Raydium integer amount")
    if not 0 <= amount < 2 ** 64:
        raise ValueError("Raydium amount outside uint64")
    return amount


def quote(position, fetch=get_json, supply_reader=token_supply, diagnostics=None):
    # Preserve completed read stages even when a later provider request fails.
    trace = diagnostics if diagnostics is not None else {}
    trace.update(failure_stage="identity", execution_verified=False)
    if position.get("chain") != "solana":
        raise ValueError("Solana only")
    mint = position["address"]
    if not isinstance(mint, str) or not 32 <= len(mint) <= 44 or any(
            c not in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in mint):
        raise ValueError("Invalid mint")
    trace["failure_stage"] = "mint_metadata"
    decimals, metadata_evidence = mint_decimals(mint, fetch, supply_reader)
    trace.update(mint_decimals=decimals, mint_metadata=metadata_evidence,
                 failure_stage="quantity")
    amount = raw_quantity(position["quantity"], decimals)
    trace.update(input_amount_raw=str(amount), output_mint=USDC,
                 slippage_bps=200, failure_stage="route_request")
    query = urllib.parse.urlencode({"inputMint": mint, "outputMint": USDC,
                                   "amount": str(amount), "slippageBps": "200", "txVersion": "V0"})
    started = time.monotonic()
    try:
        result = fetch("https://transaction-v1.raydium.io/compute/swap-base-in?" + query)
    finally:
        trace["quote_request_seconds"] = time.monotonic() - started
    trace["failure_stage"] = "route_validation"
    data = result.get("data") or {}
    if result.get("success") is not True:
        trace["provider_message"] = str(result.get("msg", "unknown"))[:160]
        raise ValueError("Provider quote unavailable: " + str(result.get("msg", "unknown"))[:160])
    if (data.get("inputMint") != mint or data.get("outputMint") != USDC
            or str(data.get("inputAmount")) != str(amount) or data.get("swapType") != "BaseIn"
            or data.get("slippageBps") != 200 or not data.get("routePlan")):
        raise ValueError("Quote identity/amount/route mismatch")
    output = raydium_uint64(data["outputAmount"])
    threshold = raydium_uint64(data["otherAmountThreshold"])
    if output <= 0 or not 0 <= threshold <= output:
        raise ValueError("Invalid quote output")
    trace["failure_stage"] = None
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


def jupiter_quote(mint, amount, fetch=get_json):
    """Keyless GET-only price check. No taker, transaction building or execution."""
    result = jupiter_pair_quote(mint, USDC, amount, fetch)
    result.update(expected_out_usdc=int(result["output_amount_raw"]) / 1_000_000,
                  threshold_usdc=int(result["threshold_amount_raw"]) / 1_000_000)
    return result


def jupiter_pair_quote(mint, output_mint, amount, fetch=get_json):
    """Validate both sides of an ExactIn quote; output remains integer token units."""
    if (not isinstance(mint, str) or not 32 <= len(mint) <= 44 or any(
            c not in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in mint)
            or not isinstance(output_mint, str) or not 32 <= len(output_mint) <= 44 or any(
                c not in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in output_mint)
            or not isinstance(amount, str) or not amount.isascii() or not amount.isdigit()
            or not 0 < int(amount) < 2 ** 64):
        raise ValueError("Invalid Jupiter mint/amount")
    query = urllib.parse.urlencode({"inputMint": mint, "outputMint": output_mint, "amount": amount})
    started = time.monotonic()
    data = fetch("https://api.jup.ag/swap/v2/order?" + query)
    if data.get("error") or data.get("errorCode") or data.get("errorMessage"):
        raise ValueError("Jupiter provider error: " + str(data.get("error") or data.get("errorMessage") or data.get("errorCode"))[:160])
    if (data.get("inputMint") != mint or data.get("outputMint") != output_mint
            or data.get("inAmount") != amount or data.get("swapMode") != "ExactIn"
            or data.get("transaction") is not None or data.get("taker")
            or data.get("router") not in {"metis", "jupiterz", "dflow", "okx"}):
        raise ValueError("Jupiter quote identity/amount/router or quote-only mismatch")
    output, threshold = data.get("outAmount"), data.get("otherAmountThreshold")
    if (not isinstance(output, str) or not output.isascii() or not output.isdigit()
            or not 0 < int(output) < 2 ** 64
            or not isinstance(threshold, str) or not threshold.isascii() or not threshold.isdigit()
            or not 0 <= int(threshold) <= int(output)):
        raise ValueError("Invalid Jupiter output/threshold")
    return {"status": "QUOTE_ONLY", "provider": "Jupiter Swap V2 keyless",
            "input_amount_raw": amount, "output_mint": output_mint,
            "output_amount_raw": output, "threshold_amount_raw": threshold,
            "router": data["router"], "slippage_bps": data.get("slippageBps"),
            "fee_evidence": fee_evidence(data),
            "quote_request_seconds": time.monotonic() - started,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "market_data_age_seconds": None, "network_costs_included": False,
            "execution_verified": False}


def roundtrip_quote(mint, fetch=get_json):
    """Sequential hypothetical 5 USDC buy/sell. Never paper equity or a fill."""
    record = {"version": "roundtrip-shadow-r2", "chain": "solana", "address": mint,
              "started_at": datetime.now(timezone.utc).isoformat(), "input_usdc": 5,
              "execution_verified": False, "fx_applied": False,
              "network_cost_usdc": None, "realized_slippage_usdc": None,
              "returned_usdc": None, "quoted_roundtrip_loss_pct": None,
              "raw_roundtrip_change_pct": None, "router_changed": None,
              "interpretation_status": "INCOMPLETE",
              "failure_stage": "buy_quote"}
    try:
        buy = jupiter_pair_quote(USDC, mint, "5000000", fetch)
        record.update(buy_quote=buy, failure_stage="sell_quote")
        sell = jupiter_pair_quote(mint, USDC, buy["output_amount_raw"], fetch)
        returned = int(sell["output_amount_raw"]) / 1_000_000
        raw_change = (returned / 5 - 1) * 100
        positive_return = returned > 5
        record.update(status="QUOTE_ONLY", failure_stage=None, sell_quote=sell,
                      returned_usdc=returned,
                      raw_roundtrip_change_pct=raw_change,
                      router_changed=buy["router"] != sell["router"],
                      interpretation_status=("POSITIVE_RETURN_UNRESOLVED" if positive_return
                                             else "LOSS_PROXY_ONLY"),
                      quoted_roundtrip_loss_pct=(None if positive_return else -raw_change))
    except Exception as exc:
        record.update(http_diagnostics(exc))
        record.update(status="UNAVAILABLE", error=type(exc).__name__ + ": " + str(exc)[:240])
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    return record


class RouteShadow:
    def __init__(self, duration=900, interval=60, fetch=get_json, read=snapshots, supply_reader=token_supply):
        self.duration, self.interval = duration, interval
        self.fetch, self.read = fetch, read
        self.supply_reader = supply_reader
        self.stop_event = threading.Event()
        self.audit = QuoteAudit()
        self.cursor = 0
        self.jupiter_enabled = os.getenv("BRAIN_JUPITER_SHADOW", "1") == "1"
        self.next_jupiter_request = 0
        self.roundtrip_enabled = os.getenv("BRAIN_ROUNDTRIP_SHADOW", "1") == "1"
        self.thread = threading.Thread(target=self.run, name="paper-route-shadow")

    def start(self):
        self.audit.save()
        self.thread.start()
        print("ROUTE SHADOW r3 INICIO | Solana | read-only GET quotes + RPC mint fallback | staged failure evidence | max4 cantidades/60s | logs only | sin cambios de saldo", flush=True)
        if self.jupiter_enabled:
            print("JUPITER SHADOW r2 INICIO | keyless GET quote-only | HTTP diagnostics | marcas por posicion USDC | sin taker | separacion minima 3s | sin cambios de saldo", flush=True)
            if self.roundtrip_enabled:
                print("ROUNDTRIP SHADOW r2 INICIO | hipotetico 5 USDC | max1 token/pase | GET quote-only | sin cambios de saldo", flush=True)

    def paced_jupiter_fetch(self, url):
        if self.stop_event.wait(max(0, self.next_jupiter_request - time.monotonic())):
            raise ValueError("Shadow stopped")
        self.next_jupiter_request = time.monotonic() + 3
        return self.fetch(url)

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
            diagnostics = {}
            try:
                evidence.update(quote(item, self.fetch, self.supply_reader, diagnostics))
            except Exception as exc:
                evidence.update(diagnostics)
                evidence.update(http_diagnostics(exc))
                evidence.update(status="UNAVAILABLE", error=type(exc).__name__ + ": " + str(exc)[:240],
                                execution_verified=False)
            evidence["total_request_seconds"] = time.monotonic() - started
            self.audit.save("RAYDIUM", evidence)
            print("ROUTE SHADOW " + json.dumps(evidence, ensure_ascii=False, allow_nan=False), flush=True)
            if self.jupiter_enabled:
                comparison = {"version": "jupiter-shadow-r2", "snapshot_at": evidence["snapshot_at"],
                              **item, "execution_verified": False}
                if "input_amount_raw" not in diagnostics:
                    comparison.update(status="SKIPPED", error="Validated mint quantity unavailable")
                else:
                    wait = max(0, self.next_jupiter_request - time.monotonic())
                    if self.stop_event.wait(wait):
                        break
                    self.next_jupiter_request = time.monotonic() + 3
                    comparison.update(mint_metadata=diagnostics["mint_metadata"],
                                      input_amount_raw=diagnostics["input_amount_raw"], output_mint=USDC)
                    requested = time.monotonic()
                    try:
                        comparison.update(jupiter_quote(item["address"], diagnostics["input_amount_raw"], self.fetch))
                    except Exception as exc:
                        comparison.update(http_diagnostics(exc))
                        comparison.update(status="UNAVAILABLE", error=type(exc).__name__ + ": " + str(exc)[:240])
                    comparison["total_request_seconds"] = time.monotonic() - requested
                comparison.setdefault("received_at", datetime.now(timezone.utc).isoformat())
                comparison["position_valuations"] = position_valuations(item, comparison)
                self.audit.save("JUPITER", comparison)
                print("JUPITER SHADOW " + json.dumps(comparison, ensure_ascii=False, allow_nan=False), flush=True)
        self.cursor = (self.cursor + count) % len(items)
        if self.jupiter_enabled and self.roundtrip_enabled and not self.stop_event.is_set():
            mint = items[(self.cursor - count) % len(items)]["address"]
            result = roundtrip_quote(mint, self.paced_jupiter_fetch)
            self.audit.save("ROUNDTRIP", result)
            print("ROUNDTRIP SHADOW " + json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)

    def run(self):
        started = time.monotonic()
        while not self.stop_event.is_set() and time.monotonic() - started < self.duration:
            try:
                self.tick()
            except Exception as exc:
                print(f"ROUTE SHADOW ERROR {type(exc).__name__}: {exc}", flush=True)
            self.stop_event.wait(min(self.interval, max(0, self.duration - (time.monotonic() - started))))



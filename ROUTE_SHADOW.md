# Route shadow r3

Read-only parallel observation, enabled by default in `run_session`. Set
`BRAIN_ROUTE_SHADOW=0` to disable. No protected workflows changed.

An independent thread snapshots existing Solana positions with non-blocking wallet
locks. It releases every lock before network access and never writes any wallet.
Up to four distinct mint/quantity combinations per pass, with a 60 second delay
after each pass; rotation covers additional quantities. Busy wallets are skipped.
Missing positions and unsupported chains are reported. Request timeout is 5s;
provider errors remain observations and cannot trigger a sale or fail the session.
The thread is joined before session completion. There is no coverage between runs.

Raydium mint metadata identifies decimals for the exact contract. Quantity is
floored to integer base units and quoted through GET `/compute/swap-base-in`
to Solana USDC. Response identity, input amount, route, output and threshold are
validated. No transaction building, wallet, signing or transaction submission is used.
In r2, absent/invalid Raydium metadata falls back to the exact mint's read-only
Solana mainnet RPC `getTokenSupply` at confirmed commitment (HTTP POST, 5s timeout).
The response id, RPC status, slot, amount and decimals are validated. Records include
metadata source, RPC context slot and primary metadata error. This slot dates the
mint metadata, not the later route quote. Missing/invalid RPC data fails closed.
Raydium quotes themselves remain GET-only; there is no key or paid service.
Raydium coverage is not Jupiter's full routing coverage: no quote does not prove
that a token cannot be sold anywhere.

Evidence is in GitHub run logs (`ROUTE SHADOW` JSON), not wallet artifacts.
Each record identifies wallets, entry time, snapshot quantity and the existing
paper mark's timestamp/status. Positions may change or close after snapshot:
these records are not contemporaneous executions or independently funded arms.
USDC output is not EUR; historical paper quantity/mark units retain the existing
model convention. Do not sum or substitute these quotes into paper equity.
The expected output includes the provider route's pool fees; no additional fixed
paper fee/slippage is deducted here. 200bps is a quoted tolerance, not a realized
cost. Network fees and realized slippage are not measured. Data age is unknown;
receipt time and request latency are not proof of market freshness. Never call
a quote an executable fill, guaranteed stop or profit.

Primary API reference: Raydium SDK v2 demo `src/api/swap.ts` and SDK
`src/api/api.ts` (`getTokenInfo`). Offline tests run with the existing
`test_exit_watchdog.py` suite, including malformed identity, quantity bounds,
provider failure, unchanged wallet bytes and non-blocking snapshots.
Additional r2 tests reproduce missing mint metadata, exercise exact-mint RPC fallback,
reject RPC errors/invalid decimals, and verify the only RPC method is getTokenSupply.
Reference: https://solana.com/docs/rpc/http/gettokensupply

r3 preserves completed metadata/quantity stages on failed route requests. UNAVAILABLE
records include failure_stage, exact raw amount/output mint, metadata source/slot,
provider message and route-request elapsed time when reached. Previously a later
ROUTE_NOT_FOUND erased all this diagnostic evidence. Failed records never include
an expected output or imply executable liquidity. No new network requests, trading
decisions, thresholds or wallet writes are introduced. Offline regressions cover
RPC success followed by missing route, and a timeout after validated metadata.

## Jupiter comparison r1

`BRAIN_JUPITER_SHADOW=1` (default; 0 disables) adds keyless GET
`https://api.jup.ag/swap/v2/order` after each selected Raydium observation with
validated mint/quantity, including missing Raydium routes. Reuses exact raw
quantity/metadata; no additional mint RPC. Same independent shadow thread, max4
quantities/pass, 60s wait after pass, Jupiter requests spaced at least3s with
interruptible waits, HTTP timeout5s. No taker, wallet, API key, build or execute
parameter/endpoint. Errors such as authentication required or rate limits remain
UNAVAILABLE; no retries, no paid service. Missing validated quantity is SKIPPED.

JUPITER SHADOW logs are separate from Raydium and paper wallets. Validate exact
input/output mints, raw input amount, ExactIn, recognized router, no transaction
or taker, positive integer output and valid threshold. Never log raw responses.
USDC outputs do not alter EUR equity, rules, balances, reserves or risk limits.
Provider-default slippage is recorded, not forced to match Raydium200bps; amounts
are observations at different instants, not simultaneous fills. A quote is not
execution; fees, data age and keyless coverage remain unverified in production.

Docs checked7Oct2026: portal plans document keyless0.5RPS, while endpoint reference
still labels x-api-key required. Live workspace probe timed out, so only GitHub
session logs can establish keyless availability. Offline tests cannot prove it.
https://developers.jup.ag/docs/portal/plans
https://developers.jup.ag/docs/api-reference/swap/order

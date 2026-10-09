# Route shadow r3

## Quote audit r1 (9 October 2026)

`fomo_quote_audit.json` now preserves bounded Raydium, Jupiter and round-trip
observations in each run's `fomo-memory` artifact. It contains the current run ID,
session start, snapshot and quote receipt times, exact quantity, wallet references,
provider failures and per-position gross quote marks. It is an evidence sidecar,
not a portfolio. The file is reset before each Brain session; older downloaded
marks are never reused. At most 300 records are retained and dropped records are
counted. Writes replace the sidecar atomically; storage errors do not stop the
observation thread. Paper wallet files are never written by the audit.

Jupiter records retain provider-declared signature, priority and rent fees in
lamports, plus feeBps. Missing, negative or malformed fees are unknown, not zero.
Even complete declared fields are only provider estimates. Payer context, network
cost in USDC/EUR, FX, market-data age and realized slippage remain unresolved;
net liquidation remains null. Fees are not deducted from outAmount again because
provider fees may already be reflected in that quote. This does not lift the M4
entry pause, change exits or turn a read-only price check into an executed sale.

Sources checked 9 October 2026:
https://developers.jup.ag/docs/swap/order-and-execute
https://developers.jup.ag/docs/api-reference/swap/order

Offline regressions verify missing versus zero fees, unchanged gross output and
unknown net value, session reset, bounded history, wallet isolation and storage
failure. Live provider coverage must be checked in a subsequent run artifact.

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

## Jupiter diagnostics and position marks r2

Run336 (37657634712, 7Oct2026) had19 valid Jupiter quotes and26 HTTP400
responses whose bodies were discarded. The cause of those400s was therefore
unknown. The shared GET reader now reads at most4097 error bytes and parses only
complete JSON bodies of at most4096 bytes. Logs retain HTTP status and bounded
scalar error/errorCode/errorMessage/msg fields only; no raw body, headers,
transaction, nested error object or request URL. Non-JSON/oversize bodies retain
status alone. No retries or additional API requests are introduced.

JUPITER SHADOW r2 records include position_valuations, one independent snapshot
mark per wallet/contract/entry/quantity. Gross quoted USDC and provider threshold
are recorded only for a validated current response; failed/skipped quotes have
null values and never carry forward an old mark. Snapshot time, receipt time and
existing paper quote status/time remain separate. Net liquidation value, network
cost, realized slippage and market data age are unknown (null), not zero. No FX is
applied. A provider threshold is not a guaranteed fill. These are logs only, not
new portfolios or equity; do not add wallets/providers or treat marks as cash.
Tests reproduce HTTP400 propagation, bounded/non-JSON errors, wallet isolation,
unknown cost fields and rejection of stale outputs. They do not prove live
provider error codes or actual execution. Live validation needs a subsequent run.
# Round-trip quote diagnostic r2

`BRAIN_ROUNDTRIP_SHADOW=1` (default; 0 disables) logs one hypothetical
5 USDC -> open Solana mint -> USDC quote pair per shadow pass. Both calls
share Jupiter's minimum 3-second request spacing; the second uses the exact
integer output of the first. This adds at most two GET requests per pass.
The existing rotation chooses the token. This observes open tokens, not
all entry candidates, and does not filter entries or change any wallet.

`ROUNDTRIP SHADOW` records each leg's amount, router, receipt timestamp and
latency, and the sequential quoted return/loss. It also records whether the
router changed. A return above the initial 5 USDC is retained as a raw change
but classified `POSITIVE_RETURN_UNRESOLVED`; its loss proxy is null so an
inconsistent or moving quote is not presented as a negative cost or profit.
Missing or invalid legs
leave return/loss null and retain the failure stage. These sequential quotes
are not simultaneous, fills or net liquidation; movement between requests
also affects the difference. Network costs, realized slippage and market-data
age remain unknown. Output quotes may already contain provider fees; do not
add paper-model fees or infer an isolated fee cost from the difference.
USDC is not EUR. No wallet, transaction construction or execution is used.


## Strict raw output quantities (9 October 2026)

Raydium outputAmount and otherAmountThreshold accept only explicit integer values
(excluding booleans) or nonempty ASCII digit strings in the uint64 range. Floats,
signs, exponent notation, Unicode digits and overflow are rejected instead of
being coerced or truncated. Output must be positive and threshold cannot exceed
output. Jupiter retains its existing stricter string-only quantity validation.
Malformed observations remain unavailable; there is no wallet valuation, sale,
route/API change or new financial threshold. Offline tests cover both fields,
uint64 boundaries and Jupiter regressions.

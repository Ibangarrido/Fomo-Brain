# Route shadow r1

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
validated. No transaction building, wallet, signing or POST endpoints are used.
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

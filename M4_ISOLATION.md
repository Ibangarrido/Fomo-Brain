# M4 isolation r1

With `BRAIN_M4_ISOLATION=1`, five legacy EARLY, ratio and protection wallets isolate the inherited Solana M4 position. Eligibility requires the exact mint, quantity 52777.58285257178, original budget 5, opening within 2026-10-06 23:11 UTC and an unknown quote. New M4 positions and other unknown tokens do not qualify. The dedicated M4 CONTROL remains unchanged.

Isolation preserves cash, reserve, quantity, historical marks and all sales. It is not a sale or a recovery of funds. Unknown M4 contributes zero to conservative capital risk and does not occupy an active entry slot. Existing risk halts remain effective; other unknown positions still pause entries. Once a quote is verified, the position again contributes to valuation and active slots normally.

The first application records `m4_isolation_history` with balances and counts. Compare results within the same policy epoch: accumulated pre/post results are not an unchanged-policy experiment. The new 100 EUR targets portfolios are unaffected.

Jupiter gross USDC references remain indicative, expire normally, and do not establish executable net EUR proceeds. Total equity remains unknown while M4 is unvalued.


## Unknown-position isolation r1 (PAPER)

`BRAIN_UNKNOWN_ISOLATION=1` starts a separate policy epoch in V10 EARLY,
V10 IMPULSE and V11 CONTROL/NET. Only positions already unknown on the
first evaluation are eligible, identified by chain, mint and opening time.
Later unknown positions still pause entries. Eligible positions keep their
quantity, budget, historical mark and place in the maximum-three-position
limit. No sale or cash credit is created. Total equity stays unknown.
Capital risk values every unknown position at zero, with the existing 25%
loss halt, cash budget and loss cooldown unchanged. A verified quote restores
normal valuation and exit processing. Compare results within this new epoch.

V12 artifacts now report run ID, attempt, trigger, commit, engine outcome,
wallet observation age, unknown-position counts and the last entry audit.
A newly generated report over restored balances is explicitly labelled
RESTORED_OR_NOT_UPDATED; partially completed runs are labelled PARTIAL_RUN.
These fields describe local observations, not provider freshness, swap
execution, or proof that the scheduled cadence is stable.

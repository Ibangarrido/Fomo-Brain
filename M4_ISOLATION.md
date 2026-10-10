# M4 isolation r1

With `BRAIN_M4_ISOLATION=1`, five legacy EARLY, ratio and protection wallets isolate the inherited Solana M4 position. Eligibility requires the exact mint, quantity 52777.58285257178, original budget 5, opening within 2026-10-06 23:11 UTC and an unknown quote. New M4 positions and other unknown tokens do not qualify. The dedicated M4 CONTROL remains unchanged.

Isolation preserves cash, reserve, quantity, historical marks and all sales. It is not a sale or a recovery of funds. Unknown M4 contributes zero to conservative capital risk and does not occupy an active entry slot. Existing risk halts remain effective; other unknown positions still pause entries. Once a quote is verified, the position again contributes to valuation and active slots normally.

The first application records `m4_isolation_history` with balances and counts. Compare results within the same policy epoch: accumulated pre/post results are not an unchanged-policy experiment. The new 100 EUR targets portfolios are unaffected.

Jupiter gross USDC references remain indicative, expire normally, and do not establish executable net EUR proceeds. Total equity remains unknown while M4 is unvalued.

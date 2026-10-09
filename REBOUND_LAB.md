# Pair-age comparison r1 (paper only)

The experiment compares the existing EARLY rules with a single changed input:
maximum pool age 60 minutes versus 1,440 minutes (24 hours). The extended arm
can therefore observe renewed momentum in older pools, including TikTok.
This age ceiling is experimental, not evidence of a genuine rebound pattern.
It applies to all discovered candidates; no TikTok-specific buying exception.

Both wallets fork once from the existing M4 RECOVERY wallet, retaining cash,
reserve, positions, closed trades, seen contracts, loss pauses and all history.
No new 100 EUR is created and existing wallets retain their policies. Missing
fork files stop the experiment rather than silently restarting it.

Both arms inherit the exact M4 quarantine. Unverified M4 is never sold or added
to cash; total equity stays unknown. The known component must exceed 75 EUR
at the fork. The conservative 25% total-loss brake, loss pause, 5 EUR budget,
three-position limit and no reentries remain active.

All other EARLY checks remain: positive momentum in two observations, same-pool
confirmation 30-90 seconds apart, >=60% buys by count, >=40 trades/5m,
>=20,000 USD liquidity, price confirmation 1-12%, 1h rise <=150%, 5% signal
drift cap, security checks and final price refresh. Exits remain unchanged.
No buy/sell dollar-flow filter is introduced without a verified data source.

Both new wallets join the exit watchdog and are restored/saved in the artifact.
Reports compare changes in known capital, unknown quotes, open positions and
closed sale legs since the fork. Closed legs are not counts of whole trades.
Price-based fills and assumed costs do not demonstrate actual execution or
net returns. Do not sum the arms or claim a total-equity advantage while unknown.

Evaluate multiple older-token entries, realized paper outcomes, quote gaps and
drawdowns before adopting an age change in the main portfolios. Baselines and
entry_max_pair_age_minutes make the changed rule traceable.

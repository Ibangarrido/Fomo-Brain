# M4 quarantine comparison r1

Paper-only prospective CONTROL versus RECOVERY, enabled with BRAIN_M4_LAB=1.
Both arms copy fomo_lab_early_control_r1.json once, preserving cash, reserve,
positions, closed trades, seen tokens and history. A fork marker prevents a
missing arm from silently resetting capital. The existing portfolios are untouched.

RECOVERY tags only the inherited Solana M4 contract
HciAVS1urBtboqhLe59HWiMeeN2McEd6y8h4HGkrpump. It keeps this position open,
continues exit observation and retains its quantity and accounting history.
An unavailable quote for that tagged position alone no longer blocks new paper
entries. Unknown value is excluded from risk calculations, never added to cash.
Other unknown positions still block entries, including any differently addressed
token carrying a copied tag. The 25% total-loss brake applies using the known
component, conservatively assigning unknown positions zero for risk only.
This is neither an accounting write-off nor a fabricated sale. Entry budgets,
filters, reserve, loss pause and the three-position limit remain unchanged.

Exit pricing and its liquidity guard remain conservative: this experiment does
not turn the existing Jupiter gross quote into net proceeds or relax exit
verification. The independent quote audit retains route evidence for follow-up.
Original CONTROL and historical arms retain their entry pauses.

Reports show cash, reserve, known component and its change since the fork,
open/closed counts and unknown valuations. Total equity remains unknown while
any quote is unverified; total equity advantage is not claimed. Known-component
differences cannot prove total returns or execution. Arms must never be summed.
Watchdog exit-only refresh includes both new wallets; it never opens positions.
No wallet keys, signatures, builds, submissions or financial operations.

Evaluate future runs for prospective new entries, realized paper exits, drawdown
of the known component, remaining M4 uncertainty and quote coverage. Local
tests establish state isolation and risk behavior, not improved profitability.

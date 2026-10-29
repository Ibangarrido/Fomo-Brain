# Brain Clean V1 — experimental reset (PAPER ONLY)

This is a **separate experimental branch**. The previous FOMO Brain code, M4,
CONTINUATION, PATTERN PULLBACK, historical JSON files and PRs remain intact on
`main`. No historical ledger is imported into the clean experiment.

## One strategy

ESCALERA: independent market snapshots must show a peak, a 15–40% pullback,
a rebound, and a further higher breakout observation. The engine needs at least
**four observations of the same Solana pool**, separated by more than 20
seconds, and uses only observations already recorded at decision time.

The experiment uses public DexScreener search results, which are **not an
exhaustive feed**. Absence of a token from the search is not proof it is safe
or inactive. Historical performance is not inferred from future candles.

## Virtual ledger and guardrails

- Fresh initial cash: **100 EUR PAPER** (not real funds).
- Maximum virtual entry: **10 EUR**; at most **3 simultaneous positions**.
- Liquidity at least $10,000, hourly volume at least $5,000, market cap
  $30,000–$2,000,000, and at least 10 recent transactions with 50% buys.
- PAPER exits at -15% or +25% when a fresh quote is observed. Costs modelled
  as 1% per side; slippage, liquidity shocks and rugs can be worse.
- Missing price: keep position open and equity unknown; never fabricate exits.
- Rejected candidates and reasons are recorded; there is **no automatic
  parameter optimization** and no claim of predictive machine learning.

## Operation and monitoring

`.github/workflows/fomo_brain.yml` is replaced **only on this branch** by a
single clean job. Pull requests run offline tests only. Manual dispatch on
this branch executes the PAPER experiment if the workflow is available in
GitHub Actions. The 20-minute cron takes effect **only after merge to the
default branch**; the experiment is not claimed to be live beforehand.

`brain-clean-v1-state` is a branch-scoped artifact with the new ledger
(`brain_clean_v1_state.json`) and last report
(`brain_clean_v1_report.json`). It does not download `fomo-memory` or
legacy portfolio artifacts. Retention is 30 days; losing the artifact would
restart the experiment, which must be flagged in monitoring.

Follow up on the number of distinct candidates, top rejection reasons,
confirmed ESCALERA signals, PAPER entries, exits, open positions and
estimated equity (only if all positions are currently quoted). Also monitor
GitHub Actions event types: `schedule` versus `workflow_dispatch`.

**Do not merge until offline tests and an initial PAPER run are checked.**
No real trading, exchange credentials, broker orders or wallet signing.

## Faster decision loop and measurable learning

Each manual/PAPER workflow run now samples public market data **five times,
30 seconds apart** (plus source request time). The entry signal requires four observations within eight minutes. This is a bounded observation window, not a guarantee
of finding every fast-moving token. The run retains the full risk gate and
saves state after each poll. The run report aggregates all rejection reasons.

A rejected token with a verified price is tracked in a bounded watchlist.
Only a later verified quote at least **15 minutes** afterward can label the
observed price change as `rally_25pct`, `drop_30pct`, or `neutral`. These
are retrospective labels, **not proof a trade was executable or profitable**.
The strategy does not auto-change its risk thresholds based on these labels.

Fast-decision revision: the signal now needs **four** fresh snapshots within
**eight minutes**, with a 30-second wait between scans (plus network time).
Known contracts are revisited directly through DexScreener's token-pairs
endpoint (bounded to eight per scan), because search results alone are
unstable. No rule assumes a quote is guaranteed fresh or executable. Tests
must pass before promoting the PR to main.

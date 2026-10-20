# V13 prospective paper experiment

This is a separate 100 EUR virtual experiment, starting with deployment of r7.
Existing V10/V11/V12 balances and unknown positions are preserved. No wallet,
transaction signing, exchange order or on-chain execution is connected.

## Entries and exits

- Maximum 10 EUR all-in per entry; at most two open token positions.
- A qualifying early market or mature continuation must be observed twice in
  the same pool. The second observation must be 5–30 minutes later, with a
  price increase of 1–12%, positive price, >=20,000 USD liquidity and >=1,500
  USD 5-minute volume. The existing market filters are retained.
- No backfilled entries from videos or manually supplied historical prices.
  ARENA and PUNANI are manual study cases, never autonomous discovery credit.
- Modeled exits: loss of 10% of all-in capital, profit of 30%, a 15% decline
  from a peak that reached +20% in price, or age of 90 minutes. All are filled
  at the next usable observed price, which can be much worse than a stop.
- Model assumes EUR/USD=1 and a 3% cost per side. It excludes gas and MEV and
  does not verify executable sell routes. Results are price-model outcomes,
  not executable profits. Half of positive realized model profit is reserved.
- A missing/illiquid quote leaves the position open and equity unknown;
  available cash remains separate. Open positions are explicitly revisited.
- Same-token entries across multiple pools are prevented; 24-hour cooldown
  follows a close. New entries pause at <=75 EUR known modeled capital.

## Correctness and persistence

Comparisons use the same pool. Price/volume and negative transaction-count
validation prevent invalid snapshots from qualifying. The receipt timestamp
is recorded after the discovery requests; provider market freshness remains
unknown. History capacity is increased from 12,000 to 120,000 snapshots and
indexed by pool; a 24-hour time window still applies.

The main FOMO workflow is the sole automatic owner. The legacy V13 workflow
remains manually callable; both jobs share a concurrency lock. History retains
its existing cache path/key for migration. The new ledger has its own cache
and is included in report artifacts. Corrupt ledgers fail instead of resetting
capital; a missing ledger with retained r7 history also fails closed. Cache
and artifact retention are not permanent archival storage.

`trades` continues to mean verified execution and remains zero. New
`modeled_entries_this_run`, `modeled_exits_this_run` and `paper_portfolio`
fields report the experiment separately. Monitoring occurs only during runs.

Validation: `python -m unittest -v test_v13_hunter.py test_v13_paper.py`.

# Prospective opportunity audit r1

This is observation only. It never opens a wallet, signs, submits or simulates a fill.
Existing entry filters, capital brakes, wallet balances and histories are preserved.

The initial automatic cohort records received contracts with positive prices,
liquidity >= 10,000 USD and market cap/FDV between 0 and 2,000,000 USD, before
momentum and entry filters. All receive the same sampling rules: subsequent
winners and losers are retained. Identity is chain + exact base-token contract;
the most liquid received pool is selected. Pair changes are explicit.

TikTok 64oAuE88tNP7KsSyaiJTKGP4sWmLMFGWLUs9eBTLYgCp is a separate manual
case chosen AFTER its reported rise. Its baseline begins on the first new
observation, never at a reconstructed 100K capitalization. It must not be
included in aggregate automatic-cohort success rates. It is monitored directly
without adding it to the existing STUDY_TOKENS entry exclusion list.

Each record retains its first, latest and highest sampled price, observed price
change and drawdown, receipt time, unknown source freshness, pool changes,
maximum observation gap and latest entry rejection per wallet and discovery
filter. A wallet rejection may mask later filters: it does not establish that
all other entry rules would pass. No price change is called profit or net return.
Market-cap changes cannot be substituted for price returns.

TikTok and SLOPCORE EkFRff9a2jKztJHML1LG9FRmEkPJDR6XAYp3uCPdpump are
manual cases selected by the user. Each begins at its first received observation.

Up to ten automatic contracts in a rotating order plus the two manual cases are
queried per discovery cycle, including when absent from search results. Failed
quotes do not monopolize monitoring slots. This
adds at most twelve public token-pair requests; the shared market rate limiter
and exit service remain in use. No source guarantees coverage of all launches
or direct access to FOMO's launch list.

The first observation received at/after 72h freezes a record; this is not an
exact 72h valuation. Direct monitoring can retry for up to another 24h. If no
quote arrives, the last receipt time remains visible and no final value is
invented. Invalid/missing prices never become zero. Peaks are sampled, not ATH.
The cohort is capped at 500 records, never silently evicted or reset; skipped
capacity events are counted (not unique contracts). Review coverage before
starting a separately versioned subsequent cohort.

fomo_opportunity_audit_r1.json is restored/persisted in the existing artifact.
Audit errors are reported without changing wallet decisions. Offline tests
validate identity, state preservation, missing data, limits and sampling only.


## Coverage r2 — 16 October 2026

Run 1155 / artifact 12007091179 had 500 active audit rows and 83,444 cumulative
capacity-skip events (not unique missed tokens). Trump $1 Coin was in general
memory but absent from this audit. The recovered 21 received samples are in
`docs/reviews/dollar1_2026-10-15.json`. First available: 20:33:12 UTC, price
0.0001543 USD, cap 154,380 USD, buys 55.73%, 5m change -14.38%, 1h +232%.
At 20:53:16 UTC: 0.0005773 USD, cap 577,362 USD, buys 56.71%, 5m +15.67%,
1h +1140%. The maximum of these samples is NOT the token's ATH. Neither the
3.5M peak nor its timestamp was recovered. EARLY would also fail hourly and
momentum gates in these snapshots even with a funded wallet; the first printed
wallet rejection is not the only reason that can block an entry.

The automatic cohort keeps its 500 slots. Up to 100 additional slots are now
reserved for candidates actually rejected by a wallet in the current cycle,
using the same admission liquidity/cap conditions. This is a separately labelled
`automatic_rejected_overflow` cohort; do not combine its selection-biased outcomes
with the ordinary cohort. No active row is evicted, reset or relabelled. Manual
cases have 32 independent slots, including $1 selected after the event. These
are hard separate limits; skip events per pool remain visible. No limit promises
complete market coverage. Finished automatic cases keep the existing retirement
policy and cannot restart a favourable baseline.

Ten automatic watch requests remain the budget: five per cohort when both have
at least five active cases, with spare slots used by the other cohort. Rotation
moves by one each cycle, independent of price/performance and failed quotes.
Manual watches are additional; adding $1 adds one exact-contract request and
one more target in the existing rotating candle-research queue.

Snapshots now preserve `_brain_received_at` separately from `evaluated_at`.
Repeated/out-of-order receipts cannot update price, peak, counts or complete a
horizon; malformed, timezone-free and future receipts are counted and skipped.
Older records remain intact. The coverage policy change point is recorded.
This changes research coverage only: wallet brakes and entry thresholds remain.

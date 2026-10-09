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

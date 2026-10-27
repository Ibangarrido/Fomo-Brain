# M4 + CONTINUATION CONTROL: evidence-first repair checklist

Research basis: Uniswap AMM liquidity/price-impact docs; systematic trading walk-forward and no-lookahead testing. This checklist is research only; not a deployed fix.

## 1. Reconcile inherited state, never reset it
- Record immutable (chain, mint, opened_at, quantity, original budget) for each historical position.
- M4 expected HciAVS1urBtboqhLe59HWiMeeN2McEd6y8h4HGkrpump; source currently reportedly contains JIFFPOM. Verify from current fomo-memory artifact before deciding whether historical M4 is absent or archived.
- If exact legacy fingerprint does not match, do not quarantine a different token. Report mismatch; do not overwrite historical state.
- Preserve cash, reserve, closed sales, seen set, and original valuation status.

## 2. Separate accounting from eligibility
- Historical unknown mark: net value unknown, never 0 EUR equity.
- For entry risk calculations only, an explicitly pinned quarantined historical position may be excluded from the active 3-slot PAPER cap; still disclose unknown total equity.
- Any *new* unquoted position must block entries. Never isolate unknown positions automatically by filename alone.
- Assert cash and reserve identical before/after; no synthetic sale or changed closed ledger.

## 3. Integration test matrix
- CONTROL: exact pinned Coin, single historical unknown, preserved 98.58 cash and 1.08 reserve (historical fixture only); second unknown stays blocking.
- M4: exact historical fingerprint isolates once, mismatch does not; repeated run idempotent; quote unavailable does not trigger fictitious sale.
- Candidate with validated fresh quote, risk limits, and free slot can complete PAPER preflight; without quote, must not fill.
- Check same behavior with 0, 1, 2 and 3 genuinely active PAPER positions.
- Distinguish CI push, workflow_dispatch and schedule; verify a real schedule success separately.

## 4. Validate learning without hindsight
- Compare unchanged baseline versus candidate policy on identical prospective data.
- Keep zero-priced, delisted and unquotable tokens in the sample; track missing data.
- No signal may use later candles or post-decision whale actions.
- Include AMM price impact, network costs, swap fees, failed route and slippage as uncertainty.
- Require out-of-sample improvement before any parameter promotion.

## Gate to merge
No merge until full integration CI, PAPER artifact reconciliation, and scheduled-run confirmation. Never execute real financial orders.

Sources:
- https://developers.uniswap.org/docs/get-started/concepts/how-uniswap-works
- https://support.uniswap.org/hc/en-us/articles/8671539602317-What-is-price-impact
- https://www.sacaaa.org/trading/testing-strategies/

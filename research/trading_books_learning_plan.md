# FOMO Brain: evidence-based trading research syllabus (PAPER only)

This file is an original implementation roadmap inspired by publicly documented themes of financial literature. It is **not** a copy of copyrighted books, a trained model, or a deployed trading signal.

## Reading to engineering hypotheses

1. Ernest P. Chan, *Quantitative Trading*: record entry timestamp, executable reference quote, exit timestamp, slippage assumptions, net returns, and drawdown for every PAPER hypothesis.
2. Perry J. Kaufman, *Trading Systems and Methods*: formalize ESCALERA with sequential higher lows, retracement depth, breakout confirmation and volume; test against false breakouts.
3. Larry Harris, *Trading and Exchanges*: reject misleading price-only returns when liquidity, route, spread, concentration, or executable quote are unavailable.
4. Marcos Lopez de Prado, *Advances in Financial Machine Learning*: chronological train/validation/test split, embargo overlapping events, compare against simple baselines, prohibit future information in features.
5. Robert Carver, *Systematic Trading*: test volatility-adjusted PAPER position sizing and hard loss caps; do not relax existing safety gates.
6. Stefan Jansen, *Machine Learning for Algorithmic Trading*: build feature tables, log provenance and missingness, evaluate precision/recall and realized PAPER P&L out of sample.

## Experiment 1: ESCALERA versus vertical spike

- Observe each token at decision time t: pair ID, token mint, candle OHLCV, buy/sell counts, liquidity, age, market cap, whale concentration and source freshness.
- Candidate: impulse -> pullback -> higher low -> breakout above a local resistance with volume confirmation.
- Negative examples: identical initial setup that loses its higher low, collapses, or becomes unquotable.
- Measure: signal frequency, rejected-then-requalified count, max adverse excursion, quote coverage, fillability proxy, PAPER net returns and drawdowns.
- No post-t data may be used for the entry decision. Preserve discarded tokens and their subsequent outcomes, including losses.
- Report separately: market screen passed, wallet eligible, quote verified, PAPER fill simulated. Never equate these.
- Promote a change only if holdout performance improves against the unchanged baseline and safety tests pass.

## Implementation boundaries

- Do not ingest copyrighted book text into the repository; derive independently written rules and cite the titles.
- Do not assume stock-market order-book models transfer unchanged to memecoin AMMs.
- This document **does not enable learning automatically**. A collector, evaluator, baseline comparison, and verified tests are still required.
- Never place real orders, change keys, or merge unverified branches.

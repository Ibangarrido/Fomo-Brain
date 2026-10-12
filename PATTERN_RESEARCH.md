# Pattern research from meme videos — 12 October 2026

This change adds descriptive research to the existing closed 1-minute candle context. It does not change entry, exit, sizing, risk, ratio or valuation rules.

## Evidence inspected

Four user recordings from 11 October were inspected: DOPE (15:43:42, 51.4 seconds), ALON (15:47:21, 37.5 seconds), SpaceXSI (15:51:20, 24.7 seconds), CLAWHUNTER (16:16:57, 23.9 seconds). Visible shapes include a steep rise, a pullback with rebound, and consolidation after a jump. These are retrospective selected clips, not complete OHLCV histories or an unbiased sample. They cannot establish profitable entry timestamps, exit fills, or causality.

Examples visible in the clips: ALON displays 317 buys and 207 sells (~60.5% by count); CLAWHUNTER displays 64 buys and 65 sells (~49.6%). A rising chart does not imply a 75% buy-count ratio. These figures are historical UI observations, not current token data, and do not justify changing the threshold.

On 12 October around 07:48–07:49 Europe/Madrid, the public GMGN page for DOPE contract 33jENUQnjoitkMFpvNJcSHyLAHFWJuHwT6E3E8CNpump loaded without login and exposed a 1-minute chart, recent trades, liquidity and concentration. Interactive access is distinct from configured API ingestion; the running Brain's missing personal API key remains unresolved.

## Implementation

Validated context gains pattern_research, version pattern-research-r1. It uses only the five consecutive completed minute bars already validated by candle_lab. No extra API requests. Missing, stale, contradictory or incomplete bars produce no pattern evidence.

Hypotheses:
- BREAKOUT_WITH_VOLUME: last close exceeds the preceding four-bar high, is green, upper wick <=40%, volume >=1.2 times the first three-bar mean.
- PULLBACK_RECLAIM_WITH_VOLUME: penultimate bar is red, depth from the first three-bar peak to its low is 1–20%; the last green bar closes above its high, holds its low, and volume recovers.
- BREAKDOWN_WITH_VOLUME: red close below previous bar low with volume expansion.
- UPPER_REJECTION_WITH_VOLUME: upper wick >40%, close below previous close and volume expansion.
- RANGE: preceding four-bar high-to-low range <=8%, current close inside it.
- INSUFFICIENT_TRADED_VOLUME / NO_PATTERN: insufficient evidence or none of these hypotheses.

Labels and thresholds are research choices, not validated predictive rules. Their precedence and five-bar window are deliberately recorded. A pattern name can coexist with a rejected candle-r1 gate: a one-green-bar pullback reclaim still fails the existing two-green-bar entry requirement.

Contexts already flow into LAB OHLCV output, candle audits and entry context. RECOVERY uses an unfiltered observation guard; this diagnostic does not enable orders or force entries. Zero-volume intervals cannot signal demand.

## Validation and next evidence

178 offline tests passed, including four new regressions for breakout without volume, reclaim without overriding the existing gate, breakdown/rejection, future bars, stale/incomplete/contradictory bars, and zero volume.

Before turning labels into entry/exit rules, record prospective timestamps, rejected as well as accepted candidates, same contract/pool, next 1/3/5-minute returns, maximum adverse/favourable movement, fill delay, quote age and costs. Compare identical observations under the existing rule and the proposed rule; include failures and unresolved data. Videos alone cannot provide that comparison.

Official reference for OHLCV interval semantics:
https://docs.coingecko.com/websocket/wssonchainohlcv
Official GMGN command reference:
https://github.com/GMGNAI/gmgn-skills/blob/main/docs/cli-usage.md

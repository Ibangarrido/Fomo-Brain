# Exit watchdog r1 — PAPER ONLY

`BRAIN_EXIT_WATCHDOG=1` enables an independent thread during each Brain session.
It checks existing V10/LAB books without discovery, new wallets or entries.
The target is one pass every 3 seconds, not a guaranteed quote interval or fill.
The worker has a separate market cache, reused only within its current pass.
Main-thread discovery cannot clear or reuse that cache. Same-wallet read/modify/
write transactions are serialized; a busy wallet is skipped and explicitly logged,
so entry security requests can still delay exits in that particular book.
Other books continue being serviced. One-time protection/volume copies lock their
source and target books to prevent inconsistent baselines or lost writes.

Market HTTP requests are paced across both threads by host at one request per
250ms (at most about 240/minute, below the 300/minute DEX endpoint limit).
Slow requests, provider caching/429s, multiple distinct positions and independent
whale processes can reduce effective frequency. No burst catch-up is performed.
Logs include actual start-to-start pass interval and duration. Positions include
request duration and observed quote gaps; accounting uses received data, not a
fabricated stop-price fill. The worker is stopped and joined before artifact upload.

Risk, history, entry sizes, reserves and all exit thresholds remain unchanged.
DEX market prices remain indicative; no Jupiter quantity-specific route is added,
no swap is constructed, signed or submitted. Liquidity checks do not prove that a
real exit can execute. Missing/invalid quotes do not authorize virtual exits.
There is still no monitoring between GitHub runs. A persistent external service
needs a separate deployment and is not installed by this commit.

Compare complete positions after activation separately from inherited history.
Measure effective quote gaps, stop overshoot and blocked/busy passes before
claiming an improvement. A faster watcher cannot guarantee a -15% loss ceiling.

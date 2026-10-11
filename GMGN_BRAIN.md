# GMGN Brain: market-data preflight

The public GMGN token page is readable in the browser. That session is not
available to GitHub Actions and does not establish continuous market updates.

`gmgn_readonly.py` uses the official Agent OpenAPI authentication protocol and
only five fixed GET token/market endpoints: M4 info, security, pool, one-minute
candles for the previous hour, and the Solana five-minute volume ranking.
It makes at most five requests, spaces them, and stops on 401/403/429.
No signing keys, wallets, account endpoints or trade requests are used.

Configure `GMGN_API_KEY` through GitHub Actions repository secrets, never in
source or chat. Do not add a private key for this module. GMGN API key creation
requires its own public-key setup; complete that in GMGN's official UI.
Missing keys produce `MISSING_API_KEY` without network calls. The availability
of repository secrets is not assumed.

The separate job archives `gmgn_preflight.json`: availability and top-level
schema evidence only, without response values, prices or balances. Even success
means `AWAITING_SCHEMA_VALIDATION`, not an activated trading source. Confirm
actual response schemas, identity, timestamps, units, concentration definitions
and missing values before adding an adapter and isolated paper comparison.

Existing paper accounts and sources remain active. The separate GMGN paper
ledger starts once from `gmgn_paper_start_r1.json` with 100 EUR cash, no positions,
no old losses and no imported M4 holding. Subsequent runs restore `gmgn-paper`
and never reset its cash/history. Corrupt ledgers fail instead of reinitializing.
Missing keys or schema-only responses do not generate fills or market observations.
The initial browser snapshot of M4 is historical and explicitly unverified.
Planned entry size is 5 EUR (absolute limit 10 EUR), with 50% of profits reserved.
Automatic paper entries remain disabled until source/strategy validation; modeled
costs and unverified exits must remain explicit.

References checked 2026-10-11:
- https://docs.gmgn.ai/index/gmgn-agent-api
- https://github.com/GMGNAI/gmgn-skills/blob/main/src/client/OpenApiClient.ts
- https://github.com/GMGNAI/gmgn-skills/blob/main/src/client/signer.ts
- https://github.com/GMGNAI/gmgn-skills/blob/main/src/config.ts

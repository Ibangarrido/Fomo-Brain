# GMGN read-only learning protocol

GMGN data must remain separate from Clean V1 PAPER ledger. No wallet signing, trade endpoints, private keys or automatic risk changes.

1. Require official read-only API credential via GitHub Actions secret `GMGN_API_KEY`; never commit credentials.
2. Verify official endpoint host, schema, chain, token contract, quote timestamp and API rate limits before accepting data.
3. Record wallet purchases and sales only when transaction identity and timestamps can be verified. Treat social posts as correlation, not proof of causation.
4. Label observations prospectively: token, pool, timestamp, holders, smart-money wallet count, liquidity, price, volume, source and provenance.
5. Compare at least 50 independent opportunities against existing ESCALERA CONTROL in shadow mode; include rejected and failed tokens to limit selection bias.
6. Report missing coverage and failures. Never credit simulated fills on an illiquid or unquoted token.
7. Promote no signal to the PAPER strategy until a prospective validation is complete and explicitly approved.

# GMGN read-only migration

- Preserve the existing `gmgn_readonly.py` and PAPER portfolios.
- Validate connectivity using the official GMGN CLI and its documented demo credential only in a one-off test.
- Use a personal read-only API key for continuous monitoring, stored in GitHub Actions secrets.
- Compare response schemas, timestamps, token identity, and rate limits before enabling any data ingestion.
- Never configure signing keys, wallets, swaps, or live trading.
- Keep PAPER entries disabled until real market-data freshness and exit quotations are validated.

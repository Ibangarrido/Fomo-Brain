# Social radar r2 — read-only observations

Brain queries X recent search separately for `realDonaldTrump` and `elonmusk`,
without requiring crypto keywords. It reads the last 24 hours, excluding reposts,
with at most three pages of 100 posts per account per session. Keywords annotate
returned posts after retrieval. Replies/quotes may be observations; they do not
prove that the author endorses a token.

Every accepted post needs an ID, timestamp inside the window, and author ID
mapped to the requested username through X's `includes.users` expansion. Events
retain author ID, account, canonical post link, UTC timestamp, text and version.
Pagination caps, identity failures and account errors are explicitly partial
coverage, not successful full monitoring. One account failing does not discard
verified results from the other. Session memory deduplicates IDs and retains
the existing last-200-event limit; it is not a complete permanent X archive.

The API requires the existing `X_BEARER_TOKEN` and provider access/credits.
No new credential, paid service, subscription or financial operation is created.
The query runs at session start, not continuously. Photos/videos in posts are not
analyzed. A matching theme/name is not a verified token contract or trade signal.
Existing Brain logic only links an event to a token through its explicit contract;
this change does not loosen entry rules, alter costs or create mobile alerts.
The separate hourly research task sends alerts only for corroborated new events.

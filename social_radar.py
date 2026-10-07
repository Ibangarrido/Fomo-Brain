"""Public X posts as observations, never endorsements or automatic trade signals."""
from datetime import datetime, timezone, timedelta


def collect_posts(fetch, accounts, keywords, now=None, max_pages=3):
    if not 1 <= max_pages <= 3:
        raise ValueError("Social pagination must be bounded to 1-3 pages")
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    events, coverage, seen = [], {}, set()
    for account in accounts:
        report = {"status": "OK", "pages": 0, "accepted": 0, "rejected": 0,
                  "window_start": start.isoformat(), "window_end": now.isoformat(),
                  "complete": False}
        coverage[account] = report
        next_token = None
        for page in range(max_pages):
            params = {"query": f"from:{account} -is:retweet", "max_results": 100,
                      "start_time": start.isoformat(),
                      "tweet.fields": "created_at,author_id,referenced_tweets",
                      "expansions": "author_id", "user.fields": "username"}
            if next_token:
                params["next_token"] = next_token
            try:
                payload = fetch(params)
                if not isinstance(payload, dict):
                    raise ValueError("Invalid response")
                if payload.get("errors"):
                    report["status"] = "PARCIAL/ERROR"
                authors = {str(user.get("id")): str(user.get("username", "")).lower()
                           for user in (payload.get("includes") or {}).get("users", [])
                           if isinstance(user, dict)}
                posts = payload.get("data", [])
                if not isinstance(posts, list):
                    raise ValueError("Invalid posts")
                report["pages"] += 1
                for post in posts:
                    try:
                        if not isinstance(post, dict):
                            raise ValueError("Invalid post")
                        author_id = str(post.get("author_id", ""))
                        post_id = str(post.get("id", ""))
                        created = datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
                        if (not post_id.isdigit() or not author_id
                                or authors.get(author_id) != account.lower()
                                or created.tzinfo is None or not start <= created <= now
                                or any(ref.get("type") == "retweeted"
                                       for ref in post.get("referenced_tweets", []))):
                            raise ValueError("Identity/time not verified")
                        text = post.get("text")
                        if not isinstance(text, str) or not text.strip():
                            raise ValueError("Missing text")
                    except (KeyError, TypeError, ValueError, AttributeError):
                        report["rejected"] += 1
                        report["status"] = "PARCIAL/ERROR"
                        continue
                    if post_id in seen:
                        continue
                    seen.add(post_id)
                    events.append({"source": "X", "account": account,
                                   "author_id": author_id, "id": post_id,
                                   "created_at": created.isoformat(), "text": text,
                                   "url": f"https://x.com/{account}/status/{post_id}",
                                   "keywords": [k for k in keywords if k in text.lower()],
                                   "identity_verified": True, "radar_version": "social-r2"})
                    report["accepted"] += 1
                next_token = (payload.get("meta") or {}).get("next_token")
                if not next_token:
                    report["complete"] = report["status"] == "OK"
                    break
            except Exception as exc:
                report["status"] = "ERROR"
                report["error_type"] = type(exc).__name__
                break
        if next_token:
            report["status"] = "PARCIAL/LIMITE PAGINAS"
            report["complete"] = False
    status = "CONSULTA OK" if coverage and all(
        report["complete"] for report in coverage.values()) else "COBERTURA PARCIAL/ERROR"
    return sorted(events, key=lambda event: (event["created_at"], event["id"])), status, coverage

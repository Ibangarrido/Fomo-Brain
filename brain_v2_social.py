"""PAPER ONLY: classify supplied authorized public social observations."""
import math

def assess(posts, *, mint, now, window=900):
    if not isinstance(mint,str) or not mint or type(now) not in (int,float) or not math.isfinite(now) or type(window) is not int or window <= 0:
        raise ValueError("invalid scope")
    unique = {}
    for p in posts:
        if p.get("mint") != mint or p.get("mint_verified") is not True or p.get("authorized_source") is not True:
            continue
        t = p.get("timestamp")
        if type(t) not in (int,float) or not math.isfinite(t) or not now-2*window < t <= now:
            continue
        source, ident, author, fingerprint = (p.get(k) for k in ("source","post_id","author_id","text_fingerprint"))
        if not all(isinstance(x,str) and x.strip() for x in (source,ident,author,fingerprint)):
            continue
        if p.get("is_repost") is not False or p.get("is_promoted") is not False:
            continue
        key = (source,ident)
        row = (t,source,author,fingerprint)
        if key in unique and unique[key] != row:
            raise ValueError("conflicting post evidence")
        unique[key] = row
    recent = [r for r in unique.values() if r[0] > now-window]
    prior = [r for r in unique.values() if r[0] <= now-window]
    def metrics(rows):
        return len({(r[1],r[2]) for r in rows}), len({r[3] for r in rows})
    authors, distinct = metrics(recent)
    baseline, _ = metrics(prior)
    label = "MONITOR"
    if len(recent) >= 5 and distinct / len(recent) < .6:
        label = "REPETITIVE_CONTENT"
    elif baseline < 3:
        label = "INSUFFICIENT_BASELINE"
    elif authors >= 6 and authors >= 2*baseline and distinct >= 5:
        label = "SOCIAL_ACCELERATION_WATCH"
    return dict(label=label, recent_posts=len(recent), recent_author_accounts=authors,
                prior_author_accounts=baseline, distinct_content=distinct)

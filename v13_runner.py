"""V13 scheduled PAPER radar. Public DEX Screener discovery, no wallet or trading."""
import json
from collections import Counter
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from v13_hunter import scan, trend_observation, continuation_observation, mature_continuation_observation, dormant_wakeup_observation

STATE = "v13_history.json"
OUTPUT = "v13_report.json"
SEARCHES = ("pump", "meme", "solana", "graduated", "bnb", "flap")
SUPPORTED_CHAINS = ("solana", "bsc")
WATCH = (("solana", "6vwkHvvoJujaPy6SWdjqE2fFc1V3AW6pj6KTh9jipump"),
         ("solana", "8Vb5f7enGjp2uHuRqh1F5AVoXoXrYVZHwuw2orjepump"),
         ("solana", "HqmFi85adLD8BQA7en1HfajdAfzVFps5REgQaYuw6Ax8"),
         ("solana", "w16qoALFz66AEdRJM56jAAionWb5FhVyjGjznrYpump"),
         ("solana", "87sEXKPMBeoryaqFQQnq1Yq6mUvjeNzhiFGxJbRjpump"),
         ("solana", "3eYs1iGSBQTzxZ94RN8W5c4RCipUJmVbAnueFrrapump"),
         ("solana", "9rJsyktbXsmqga2Q4S2Hiwj8UaBMzbc88jBiPGaPpump"),
         ("solana", "5rqqBQSsA5fo2znzmudV3vGD6uKfe7K7wafYS9N9pump"),
         ("solana", "9JUYGis9NeLKjoHYG4A81UxikZYNg5VHZ5r5Y4xDpump"),
         ("solana", "ESABfJpt9cocXgWX7HF8WwSXrcv785oyaA8imwojpump"),
         ("solana", "9A1VFXY8ETKNSP2jN3rnTF99jDTnbR8j3JqVHas4pump"),
         ("solana", "nxPqZ4F7ux8Vph5NFu25rEP6Kx9Gr1U6Fmj36Rjpump"),
         ("solana", "D9rASpRWPyMYQGVLQLEN4S4Cy8fYE7fP8au9Gy7Upump"),
         ("solana", "ESnW5ZbLmoEAg2QEMxnMsY9R3aS8Kw58HJacYURmpump"),
         ("solana", "2qgnTgJbZU6Tu6CMrm5Z5ePDGuUAyGTACbBoBCw6pump"),
         ("bsc", "0xaacbc156435dbab7815a61bccba1c827e52a7777"),
         ("bsc", "0xb10b2c022a717a66fa627c9c9ce73779b5347777"))
MAX_HISTORY = 12000
MAX_REVISIT = 18
MAX_DORMANT_REVISIT = 12

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Fomo-Brain-V13-Paper/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as response:
        return json.load(response)

def discover(extra_watch=()):
    pairs, errors = {}, []
    def add(p, source):
        if not isinstance(p, dict):
            return
        chain, pool = p.get("chainId"), p.get("pairAddress")
        if chain in SUPPORTED_CHAINS and pool:
            key = (chain, pool)
            if key not in pairs:
                pairs[key] = dict(p, _v13_source=source)
    for term in SEARCHES:
        try:
            url = "https://api.dexscreener.com/latest/dex/search/?q=" + urllib.parse.quote(term)
            for p in (fetch(url).get("pairs") or []):
                add(p, "search:" + term)
        except Exception as exc:
            errors.append({"source": "search:" + term, "error": type(exc).__name__})
        time.sleep(.3)
    for endpoint in ("token-profiles/latest/v1", "token-profiles/recent-updates/v1"):
        try:
            profiles = fetch("https://api.dexscreener.com/" + endpoint)
            for p in profiles[:20] if isinstance(profiles, list) else []:
                if p.get("chainId") not in SUPPORTED_CHAINS or not p.get("tokenAddress"):
                    continue
                url = "https://api.dexscreener.com/token-pairs/v1/" + p["chainId"] + "/" + urllib.parse.quote(p["tokenAddress"])
                for found in fetch(url) or []:
                    add(found, "profile:" + endpoint)
                time.sleep(.3)
        except Exception as exc:
            errors.append({"source": endpoint, "error": type(exc).__name__})
    # Paid visibility is a discovery source, not evidence of organic demand.
    for endpoint in ("token-boosts/latest/v1", "token-boosts/top/v1",
                     "community-takeovers/latest/v1"):
        try:
            promoted = fetch("https://api.dexscreener.com/" + endpoint)
            for item in promoted[:20] if isinstance(promoted, list) else []:
                if not isinstance(item, dict) or item.get("chainId") not in SUPPORTED_CHAINS or not item.get("tokenAddress"):
                    continue
                url = "https://api.dexscreener.com/token-pairs/v1/" + item["chainId"] + "/" + urllib.parse.quote(item["tokenAddress"])
                for found in fetch(url) or []:
                    add(found, "promotion:" + endpoint)
                time.sleep(.3)
        except Exception as exc:
            errors.append({"source": endpoint, "error": type(exc).__name__})
    for chain, address in dict.fromkeys((*WATCH, *extra_watch)):
        try:
            url = "https://api.dexscreener.com/token-pairs/v1/" + chain + "/" + urllib.parse.quote(address)
            for found in fetch(url) or []:
                add(found, "watch")
        except Exception as exc:
            errors.append({"source": "watch", "error": type(exc).__name__})
    return list(pairs.values()), errors

def select_revisits(prior, now):
    """Reserve follow-up slots for quiet tokens, not only past winners.

    Latest snapshot per token prevents ancient alerts from dominating. Quiet
    candidates require a valid, liquid, sub-$2m market and recent observation.
    """
    latest = {}
    for row in prior:
        key = (row.get("chain"), row.get("address"))
        if key[0] not in SUPPORTED_CHAINS or not isinstance(key[1], str) or not key[1]:
            continue
        try:
            stamp = datetime.fromisoformat(row["received_at"])
            if not now-timedelta(hours=6) <= stamp <= now:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        if key not in latest or stamp > latest[key][0]:
            latest[key] = (stamp, row)
    alerts, quiet = [], []
    for key, (stamp, row) in latest.items():
        if (row.get("discovery_alert") or row.get("trend_watch") or
            row.get("continuation_watch") or row.get("mature_watch") or
            row.get("dormant_wakeup_watch")):
            alerts.append((stamp, key))
        if (row.get("volume_5m_usd") is not None and
            0 <= row["volume_5m_usd"] <= 1000 and
            row.get("trades_5m") is not None and
            0 <= row["trades_5m"] <= 10 and
            row.get("liquidity_usd") is not None and
            row["liquidity_usd"] >= 20000 and
            row.get("market_cap_usd") is not None and
            0 < row["market_cap_usd"] <= 2000000 and
            row.get("pair_age_minutes") is not None and
            row["pair_age_minutes"] >= 60):
            quiet.append((stamp, key))
    alerts.sort(reverse=True)
    quiet.sort(reverse=True)
    active = [key for _, key in alerts[:MAX_REVISIT]]
    dormant = [key for _, key in quiet if key not in active][:MAX_DORMANT_REVISIT]
    return tuple(active + dormant), len(dormant)


def discovery_timing_audit(observations, prior, manual_watch):
    """Audit discovery timing using only recorded snapshots, never backfill.

    'PRE_IMPULSE_CANDIDATE' means first observation was not already extended
    by 1h change; it does NOT establish that a later x5 occurred.
    """
    earliest = {}
    first_alert = {}
    for row in (*prior, *observations):
        key = (row.get("chain"), row.get("address"))
        stamp = row.get("received_at")
        if not all(isinstance(x, str) and x for x in (*key, stamp)):
            continue
        if key not in earliest or stamp < earliest[key]["received_at"]:
            earliest[key] = row
        if row.get("discovery_alert") and (key not in first_alert or stamp < first_alert[key]):
            first_alert[key] = stamp
    counts = Counter()
    for row in observations:
        key = (row.get("chain"), row.get("address"))
        first = earliest.get(key, row)
        pct = first.get("change_1h_pct")
        source = first.get("source", "unknown")
        manual = key in manual_watch
        if manual:
            stage = "MANUAL_CASE_NOT_AUTONOMOUS"
        elif pct is None or not isinstance(pct, (int, float)):
            stage = "FIRST_OBSERVATION_MOMENTUM_UNKNOWN"
        elif pct >= 150:
            stage = "FIRST_SEEN_ALREADY_OVER_150PCT_1H"
        elif pct >= 50:
            stage = "FIRST_SEEN_ALREADY_OVER_50PCT_1H"
        else:
            stage = "PRE_IMPULSE_CANDIDATE_UNVERIFIED"
        row["discovery_timing_stage"] = stage
        row["first_observed_at"] = first.get("received_at")
        row["first_observed_1h_pct"] = pct
        row["first_observed_source"] = source
        row["first_alert_at"] = first_alert.get(key)
        counts[stage] += 1
    return dict(counts)


def main():
    now = datetime.now(timezone.utc)
    # Revisit previous promising tokens even if search no longer returns them.
    prior = []
    if os.path.exists(STATE):
        try:
            with open(STATE) as handle:
                data = json.load(handle)
            if isinstance(data, list):
                prior = [r for r in data if isinstance(r, dict)]
        except (OSError, ValueError, TypeError):
            pass
    extra_watch, dormant_revisit_count = select_revisits(prior, now)
    pairs, errors = discover(extra_watch)
    observations = scan(pairs, now)
    sources = {(p.get("chainId"), (p.get("baseToken") or {}).get("address"), p.get("pairAddress")): p.get("_v13_source", "unknown") for p in pairs}
    for row in observations:
        row["source"] = sources.get((row["chain"], row["address"], row["pair"]), "unknown")
    history = []
    if os.path.exists(STATE):
        try:
            with open(STATE) as handle:
                previous = json.load(handle)
            if isinstance(previous, list):
                history = [r for r in previous if isinstance(r, dict) and
                           isinstance(r.get("received_at"), str) and
                           datetime.fromisoformat(r["received_at"]) >= now - timedelta(hours=24)]
        except (OSError, ValueError, TypeError):
            errors.append({"source": "history", "error": "UNREADABLE"})
    # Enrich using only PREVIOUS snapshots. No lookahead or invented OHLC candles.
    observations = [dormant_wakeup_observation(mature_continuation_observation(continuation_observation(trend_observation(row, history), history), history), history) for row in observations]
    # Timing audit is computed before truncation and before current rows are saved.
    timing_counts = discovery_timing_audit(observations, history, set(WATCH))
    # Keep all observations, including rejects; never infer a trade from an API receipt.
    history = (history + observations)[-MAX_HISTORY:]
    with open(STATE + ".tmp", "w") as f:
        json.dump(history, f, indent=2, allow_nan=False)
    os.replace(STATE + ".tmp", STATE)
    # Explain zero qualifying signals without weakening any safety gate.
    blocker_counts = Counter(reason for row in observations for reason in row["blockers"])
    alert_blocker_counts = Counter(reason for row in observations if row["discovery_alert"] for reason in row["blockers"])
    first_seen = {}
    for item in history:
        key = (item.get("chain"), item.get("address"))
        stamp = item.get("received_at")
        if all(isinstance(v, str) and v for v in key) and isinstance(stamp, str):
            if key not in first_seen or stamp < first_seen[key]:
                first_seen[key] = stamp
    for row in observations:
        # first_observed_at comes from the timing audit, before truncation.
        row["manually_watchlisted"] = (row["chain"], row["address"]) in WATCH
        row["independently_discovered_this_run"] = row.get("source", "").startswith(("search:", "profile:")) and not row["manually_watchlisted"]
    autonomous_alerts = [row for row in observations if row["discovery_alert"] and row["independently_discovered_this_run"]]
    promoted_alerts = [row for row in observations if row["discovery_alert"] and row.get("source", "").startswith("promotion:")]
    near_misses = sorted((row for row in observations if row["discovery_alert"] and not row["market_gates_pass"]),
                         key=lambda row: (len(row["blockers"]), -(row["trades_5m"] or 0)))[:20]
    report = {"version": "v13-hunter-r6-extended-age-research", "at": now.isoformat(), "paper_only": True,
              "execution_verified": False, "trades": 0, "pairs_discovered": len(pairs),
              "observed": len(observations), "revisited_tokens_requested": len(extra_watch),
              "dormant_revisits_requested": dormant_revisit_count, "alerts": sum(r["discovery_alert"] for r in observations),
              "autonomous_discovery_alerts": len(autonomous_alerts),
              "promotion_sourced_alerts": len(promoted_alerts),
              "discovery_timing_counts": timing_counts,
              "discovery_timing_note": "Only earliest snapshot retained in 24h history; pre-impulse candidate is NOT a proven pre-x5 signal",
              "dormant_wakeup_watches": sum(r["dormant_wakeup_watch"] for r in observations),
              "dormant_sufficient_history": sum(r["dormant_data_sufficient"] for r in observations),
              "promotion_source_note": "Paid boosts/takeovers are visibility signals, NOT proof of organic demand or an entry",
              "blocker_counts": dict(blocker_counts.most_common()),
              "alert_blocker_counts": dict(alert_blocker_counts.most_common()),
              "market_gate_passes": sum(r["market_gates_pass"] for r in observations),
              "early_age_window_minutes": [2, 90],
              "mature_age_window_minutes": [60, 720],
              "trend_4h_watches": sum(r["trend_watch"] for r in observations),
              "continuation_watches": sum(r["continuation_watch"] for r in observations),
              "mature_1_12h_watches": sum(r["mature_watch"] for r in observations),
              "mature_1_12h_sufficient_data": sum(r["mature_data_sufficient"] for r in observations),
              "continuation_sufficient_data": sum(r["continuation_data_sufficient"] for r in observations),
              "research_buy_pressure_55pct": sum(r["continuation_buy_pressure_research"] for r in observations),
              "trend_4h_sufficient_data": sum(r["trend_data_sufficient"] for r in observations),
              "trend_4h_method": "timestamped observations; >=4h history required, not OHLC candles",
              "history_observations_24h": len(history),
              "source_coverage": "partial: Solana + BSC DEX search/profiles/boosts/takeovers/manual watch; not social-media post monitoring or full launch stream",
              "errors": errors,
              "top_near_misses": near_misses,
              "top_dormant_wakeups": [r for r in observations if r["dormant_wakeup_watch"]][:30],
              "top_discovery_timing": sorted((r for r in observations if r["discovery_alert"]), key=lambda r: r.get("first_observed_at") or "")[:30],
              "top_autonomous_alerts": sorted(autonomous_alerts, key=lambda r: r["trades_5m"] or 0, reverse=True)[:30],
              "top_mature_continuations": sorted((r for r in observations if r["mature_watch"]),
                                                 key=lambda r: r["trades_5m"] or 0, reverse=True)[:30],
              "top_continuations": sorted((r for r in observations if r["continuation_watch"]),
                                          key=lambda r: r["continuation_relative_volume"] or 0, reverse=True)[:30],
              "top_trends": sorted((r for r in observations if r["trend_watch"]),
                                   key=lambda r: r["trend_4h_pct_observed"] or 0, reverse=True)[:30],
              "top_alerts": sorted((r for r in observations if r["discovery_alert"]),
                                   key=lambda r: (r["market_gates_pass"], r["trades_5m"] or 0),
                                   reverse=True)[:30]}
    with open(OUTPUT, "w") as f:
        json.dump(report, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in report.items() if k not in ("top_alerts", "top_continuations", "top_trends", "top_mature_continuations", "top_near_misses", "top_autonomous_alerts", "top_dormant_wakeups", "top_discovery_timing")}, ensure_ascii=False))

if __name__ == "__main__":
    main()

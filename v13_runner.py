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
SEARCHES = ("pump", "meme", "solana", "graduated")
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
         ("solana", "ESnW5ZbLmoEAg2QEMxnMsY9R3aS8Kw58HJacYURmpump"))
MAX_HISTORY = 12000
MAX_REVISIT = 18

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
        if chain == "solana" and pool:
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
                if p.get("chainId") != "solana" or not p.get("tokenAddress"):
                    continue
                url = "https://api.dexscreener.com/token-pairs/v1/solana/" + urllib.parse.quote(p["tokenAddress"])
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
                if not isinstance(item, dict) or item.get("chainId") != "solana" or not item.get("tokenAddress"):
                    continue
                url = "https://api.dexscreener.com/token-pairs/v1/solana/" + urllib.parse.quote(item["tokenAddress"])
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
    candidates = {}
    for r in prior:
        key = (r.get("chain"), r.get("address"))
        if key[0] == "solana" and isinstance(key[1], str) and key[1] and (
                r.get("discovery_alert") or r.get("trend_watch") or r.get("continuation_watch") or r.get("mature_watch") or r.get("dormant_wakeup_watch")):
            candidates[key] = r.get("received_at", "")
    extra_watch = tuple(k for k, _ in sorted(candidates.items(), key=lambda item: item[1], reverse=True)[:MAX_REVISIT])
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
        row["first_observed_at"] = first_seen.get((row["chain"], row["address"]))
        row["manually_watchlisted"] = (row["chain"], row["address"]) in WATCH
        row["independently_discovered_this_run"] = row.get("source", "").startswith(("search:", "profile:")) and not row["manually_watchlisted"]
    autonomous_alerts = [row for row in observations if row["discovery_alert"] and row["independently_discovered_this_run"]]
    promoted_alerts = [row for row in observations if row["discovery_alert"] and row.get("source", "").startswith("promotion:")]
    near_misses = sorted((row for row in observations if row["discovery_alert"] and not row["market_gates_pass"]),
                         key=lambda row: (len(row["blockers"]), -(row["trades_5m"] or 0)))[:20]
    report = {"version": "v13-hunter-r6-extended-age-research", "at": now.isoformat(), "paper_only": True,
              "execution_verified": False, "trades": 0, "pairs_discovered": len(pairs),
              "observed": len(observations), "revisited_tokens_requested": len(extra_watch), "alerts": sum(r["discovery_alert"] for r in observations),
              "autonomous_discovery_alerts": len(autonomous_alerts),
              "promotion_sourced_alerts": len(promoted_alerts),
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
              "source_coverage": "partial: DEX search + profiles + boosts + community takeovers + manual watch; not social-media post monitoring or full launch stream",
              "errors": errors,
              "top_near_misses": near_misses,
              "top_dormant_wakeups": [r for r in observations if r["dormant_wakeup_watch"]][:30],
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
    print(json.dumps({k: v for k, v in report.items() if k not in ("top_alerts", "top_continuations", "top_trends", "top_mature_continuations", "top_near_misses", "top_autonomous_alerts", "top_dormant_wakeups")}, ensure_ascii=False))

if __name__ == "__main__":
    main()

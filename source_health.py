"""Offline, read-only source health. Never makes network requests or trades."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

SOURCES = {
    "geckoterminal": "discovery_watch.json",
    "gmgn": "gmgn_preflight.json",
    "v13": "v13_report.json",
    "cooker": "cooker_tracking_r1.json",
}

def _time(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except ValueError:
        return None

def assess(source, payload, now=None, max_age_minutes=60):
    """Distinguish process completion from validated, fresh market data."""
    if source not in SOURCES:
        raise ValueError("Unknown source")
    if not isinstance(payload, dict):
        return {"state": "INVALID", "reason": "not_an_object"}
    now = now or datetime.now(timezone.utc)
    if source == "geckoterminal":
        status = payload.get("status")
        if status != "OK":
            return {"state": "UNAVAILABLE", "reason": str(status or "missing_status")[:100]}
        if not isinstance(payload.get("candidates"), list):
            return {"state": "INVALID", "reason": "missing_candidates_array"}
        timestamp = payload.get("at")
    elif source == "gmgn":
        status = payload.get("status")
        if status == "MISSING_API_KEY":
            return {"state": "AUTH_REQUIRED", "reason": "gmgn_api_key_missing"}
        if status == "AWAITING_SCHEMA_VALIDATION":
            return {"state": "UNVALIDATED", "reason": "response_schema_not_validated"}
        if status != "VALIDATED_READ_ONLY":
            return {"state": "UNAVAILABLE", "reason": str(status or "missing_status")[:100]}
        timestamp = payload.get("received_at")
    elif source == "v13":
        if payload.get("paper_only") is not True:
            return {"state": "INVALID", "reason": "paper_only_not_confirmed"}
        errors = payload.get("errors")
        if not isinstance(errors, list):
            return {"state": "INVALID", "reason": "missing_errors_array"}
        if errors:
            return {"state": "DEGRADED", "reason": "provider_errors_present", "error_count": len(errors)}
        timestamp = payload.get("at")
    else:
        status = payload.get("status")
        if status in ("BASELINE_SET", "WAITING_FOR_BASELINE"):
            return {"state": "WARMING_UP", "reason": status.lower()}
        if status != "SYNCED":
            return {"state": "DEGRADED", "reason": str(status or "missing_status")[:100]}
        timestamp = payload.get("checked_at")
    dt = _time(timestamp)
    if dt is None:
        return {"state": "UNKNOWN_FRESHNESS", "reason": "missing_or_invalid_timestamp"}
    age = (now - dt).total_seconds() / 60
    if age < -5:
        return {"state": "INVALID", "reason": "timestamp_in_future"}
    if age > max_age_minutes:
        return {"state": "STALE", "reason": "observation_too_old", "age_minutes": round(age, 1)}
    return {"state": "HEALTHY", "reason": "report_valid_and_recent", "age_minutes": round(max(age, 0), 1)}

def audit(paths=None, now=None, max_age_minutes=60):
    paths = paths or SOURCES
    results = {}
    for name, path in paths.items():
        if name not in SOURCES:
            raise ValueError("Unknown source")
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            results[name] = {"state": "NOT_OBSERVED", "reason": "report_missing"}
        except (OSError, ValueError):
            results[name] = {"state": "INVALID", "reason": "report_unreadable"}
        else:
            results[name] = assess(name, payload, now=now, max_age_minutes=max_age_minutes)
    return {"version": "source-health-r1", "observed_at": (now or datetime.now(timezone.utc)).isoformat(),
            "read_only": True, "trading_enabled": False, "sources": results,
            "healthy_count": sum(v["state"] == "HEALTHY" for v in results.values()),
            "observed_count": sum(v["state"] != "NOT_OBSERVED" for v in results.values())}

def main():
    parser = argparse.ArgumentParser(description="Offline market-source health audit")
    parser.add_argument("--source", choices=sorted(SOURCES), action="append")
    parser.add_argument("--max-age-minutes", type=int, default=60)
    parser.add_argument("--output", default="source_health_report.json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if args.max_age_minutes < 1:
        parser.error("max-age-minutes must be positive")
    paths = {s: SOURCES[s] for s in (args.source or SOURCES)}
    report = audit(paths, max_age_minutes=args.max_age_minutes)
    target = Path(args.output)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(target)
    print("SOURCE HEALTH " + json.dumps(report, ensure_ascii=False, allow_nan=False))
    if args.strict and any(v["state"] != "HEALTHY" for v in report["sources"].values()):
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only confirmation coach: explain why recognized patterns do not enter PAPER.

Only local receipt timing is analyzed. No provider freshness, market eligibility,
order execution or scheduling is inferred.
"""
from collections import Counter
from datetime import datetime, timezone
import math

MAX_EVENTS = 150
MAX_EXAMPLES = 8


def _timestamp(value):
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def _number(value):
    return (isinstance(value, (float, int)) and not isinstance(value, bool)
            and math.isfinite(value))


def diagnose(rows, now=None):
    """Summarize blockers and pending follow-ups without authorizing a trade."""
    now = now or datetime.now(timezone.utc)
    counts = Counter()
    latest = {}
    for event in rows[-MAX_EVENTS:]:
        if not isinstance(event, dict):
            counts["invalid_event"] += 1
            continue
        stamp = _timestamp(event.get("at"))
        if stamp is None or stamp > now:
            counts["invalid_event_time"] += 1
            continue
        chain, address = event.get("chain"), event.get("address")
        if not isinstance(chain, str) or not isinstance(address, str) or not chain or not address:
            counts["missing_contract"] += 1
            continue
        status = event.get("status")
        reasons = event.get("reasons", [])
        if not isinstance(reasons, list):
            reasons = []
        if status == "INVALID_FRESH_RECEIPT" or "FRESH_RECEIPT_INVALID" in reasons:
            category = "invalid_receipt"
        elif "IDENTITY_CHANGED" in reasons or event.get("reference_pair") != event.get("current_pair"):
            category = "pair_changed"
        elif "PRICE_DRIFT_GT_5PCT" in reasons or "PRICE_DRIFT_UNKNOWN" in reasons:
            category = "quote_drift"
        elif "REFERENCE_EXPIRED_OR_INVALID" in reasons:
            category = "reference_expired"
        elif status == "RENEWED":
            category = "new_confirmation_needed"
        elif status == "REFERENCE_AVAILABLE":
            category = "reference_available_not_entry"
        else:
            category = "other"
        counts[category] += 1
        key = (chain, address)
        # Ignore out-of-order historical events when choosing the latest status.
        if key not in latest or stamp >= latest[key][0]:
            latest[key] = (stamp, event, category)
    pending = []
    for (chain, address), (stamp, event, category) in latest.items():
        if category not in ("reference_expired", "new_confirmation_needed", "quote_drift"):
            continue
        age = (now - stamp).total_seconds()
        fresh_age = event.get("fresh_receipt_age_seconds")
        window = event.get("confirmation_window_seconds")
        if not (_number(fresh_age) and 0 <= fresh_age <= 30
                and _number(window) and window in (90, 120)):
            continue
        # This is a diagnostic suggestion, not a timed fetch or valid receipt.
        # Do not keep a stale candidate pending indefinitely.
        remaining = window - (age + fresh_age)
        if remaining < 30:
            continue
        pending.append({
            "chain": chain, "address": address, "last_event_at": stamp.isoformat(),
            "blocker": category, "suggested_recheck_after_seconds": max(30, round(30 - fresh_age)),
            "window_remaining_seconds_estimate": round(remaining),
            "entry_authorized": False,
        })
    pending.sort(key=lambda x: (x["window_remaining_seconds_estimate"],
                                x["chain"], x["address"]))
    return {
        "version": "confirmation-coach-r1",
        "at": now.isoformat(), "events_considered": sum(counts.values()),
        "blockers": dict(sorted(counts.items())),
        "pending_recheck_candidates": len(pending),
        "pending_examples": pending[:MAX_EXAMPLES],
        "automatic_fetches": False, "entry_authorized": False,
        "scope": "Local receipt diagnostics only; suggestions are not quote validity, full entry eligibility, provider freshness or fills. No portfolio or strategy mutations.",
    }


def report_paper_files(paths, now=None):
    """Read PAPER memories, produce a separate diagnostic report only."""
    import json
    from pathlib import Path
    now = now or datetime.now(timezone.utc)
    reports = {}
    for filename in paths:
        path = Path(filename)
        if not path.is_file():
            reports[path.name] = {"status": "missing_file"}
            continue
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or not isinstance(state.get("confirmation_audit", []), list):
                raise ValueError("invalid confirmation memory")
            reports[path.name] = {"status": "analyzed", **diagnose(state.get("confirmation_audit", []), now)}
        except (OSError, ValueError, TypeError) as exc:
            reports[path.name] = {"status": "unreadable", "error_type": type(exc).__name__}
    return {"version": "confirmation-coach-files-r1", "at": now.isoformat(),
            "reports": reports, "wallet_state_modified": False,
            "entry_authorized": False}


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    filenames = sys.argv[1:] or [
        "fomo_lab_m4_fresh_r1.json",
        "fomo_lab_continuation_control_r1.json",
        "fomo_lab_pattern_pullback_r1.json",
        "fomo_lab_shallow_pullback_r1.json",
    ]
    report = report_paper_files(filenames)
    Path("confirmation_coach_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print("CONFIRMATION COACH REPORT " + json.dumps(report, allow_nan=False))

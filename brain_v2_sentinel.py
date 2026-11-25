"""Read-only PAPER2 health checks; never writes or executes trades."""
import math
from datetime import datetime

def audit(state, previous=None, now=None, max_gap=60):
    issues = []
    if state.get("portfolio_id") != "clean-v1-paper-2":
        issues.append("WRONG_PORTFOLIO")
    cash = state.get("cash")
    if isinstance(cash, bool) or not isinstance(cash, (int, float)) or not math.isfinite(cash) or cash < 0:
        issues.append("INVALID_CASH")
    closed = state.get("closed", [])
    ids = [row.get("id") for row in closed]
    if any(not isinstance(i, str) or not i for i in ids):
        issues.append("MISSING_CLOSED_ID")
    elif len(ids) != len(set(ids)):
        issues.append("DUPLICATE_CLOSED_ID")
    if len(state.get("positions", {})) > 3:
        issues.append("POSITION_LIMIT")
    if previous is not None:
        if previous.get("paper2_epoch") != state.get("paper2_epoch"):
            issues.append("EPOCH_CHANGED")
        if any(row not in closed for row in previous.get("closed", [])):
            issues.append("CLOSED_HISTORY_CHANGED")
    stamp = (state.get("last_run") or {}).get("completed_at")
    try:
        age = ((now or datetime.now().astimezone()) - datetime.fromisoformat(stamp)).total_seconds()
        if age < 0 or age > max_gap:
            issues.append("STALE_OR_FUTURE_RUN")
    except (TypeError, ValueError):
        issues.append("UNKNOWN_RUN_TIME")
    return {"scope": "PAPER_ONLY_READ_ONLY", "issues": issues,
            "cash": cash, "closed_count": len(closed),
            "open_count": len(state.get("positions", {})),
            "run_id": (state.get("last_run") or {}).get("id")}

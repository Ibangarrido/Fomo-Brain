"""Prospective, read-only feedback from rejected-token receipt checkpoints.

This is a learning *evaluation* loop, not a trading strategy. It cannot change
entry gates, wallet balances, quotes or execute PAPER/real orders.
"""
from collections import defaultdict
from datetime import datetime, timezone
import math

HORIZONS = ("5m", "15m")
MIN_EVIDENCE = 20
MAX_REASON_LENGTH = 120


def _utc(value):
    try:
        stamp = datetime.fromisoformat(value)
        return stamp if stamp.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def _reason_group(reason):
    reason = str(reason).lower()
    if "cartera sin valoracion" in reason:
        return "historic_valuation"
    if "senal renovada" in reason or "confirmacion" in reason or "primera lectura" in reason:
        return "confirmation_wait"
    if "ratio compras" in reason:
        return "buy_pressure"
    if "momentum" in reason:
        return "momentum"
    if "liquidez" in reason:
        return "liquidity"
    if "actividad" in reason or "trades" in reason:
        return "activity"
    if "vela" in reason or "retroceso" in reason:
        return "candle_or_pullback"
    return "other"


def evaluate(state, now=None):
    """Aggregate only timely, same-pool, forward observations.

    Checkpoints describe sampled prices, not candle highs, executable fills,
    profits, or proof that a rejected trade would have passed all guards.
    """
    now = now or datetime.now(timezone.utc)
    groups = defaultdict(lambda: {"eligible": 0, "up20": 0, "down20": 0,
                                  "sum_pct": 0.0, "contracts": set()})
    excluded = defaultdict(int)
    rows = state.get("tokens", {})
    for row in rows.values():
        if row.get("cohort") == "manual_after_event":
            excluded["manual_after_event"] += 1
            continue
        baseline = row.get("first_rejection")
        if not isinstance(baseline, dict):
            continue
        first_at = _utc(baseline.get("received_at"))
        if first_at is None or first_at > now:
            excluded["invalid_rejection_time"] += 1
            continue
        reasons = baseline.get("entry_rejections", {})
        if not isinstance(reasons, dict) or not reasons:
            excluded["missing_rejection_reason"] += 1
            continue
        # Each token contributes at most once to each reason-group/horizon.
        reasons_by_group = {_reason_group(reason)
                            for reason in reasons.values()
                            if isinstance(reason, str)}
        if not reasons_by_group:
            excluded["missing_rejection_reason"] += 1
            continue
        checkpoints = row.get("post_rejection_checkpoints", {})
        for horizon in HORIZONS:
            checkpoint = checkpoints.get(horizon)
            if not isinstance(checkpoint, dict):
                excluded["missing_" + horizon] += 1
                continue
            observed_at = _utc(checkpoint.get("observed_at"))
            lag = checkpoint.get("lag_seconds")
            change = checkpoint.get("price_change_pct")
            if observed_at is None or observed_at <= first_at or observed_at > now:
                excluded["invalid_time_" + horizon] += 1
                continue
            if not isinstance(lag, (float, int)) or isinstance(lag, bool) or not 0 <= lag <= 120:
                excluded["late_" + horizon] += 1
                continue
            # The stored lag must agree with the two actual receipt timestamps.
            # Otherwise a stale 30m observation mislabeled as a 5m checkpoint
            # would be incorrectly treated as timely learning evidence.
            actual_lag = (observed_at - first_at).total_seconds() - int(horizon[:-1]) * 60
            if abs(actual_lag - lag) > 1:
                excluded["inconsistent_lag_" + horizon] += 1
                continue
            if checkpoint.get("pair_changed") is not False:
                excluded["pair_unverified_" + horizon] += 1
                continue
            if not isinstance(change, (int, float)) or isinstance(change, bool) or not math.isfinite(change):
                excluded["invalid_price_" + horizon] += 1
                continue
            contract = (row.get("chain"), row.get("address"))
            for group in reasons_by_group:
                stats = groups[(horizon, group)]
                if contract in stats["contracts"]:
                    continue
                stats["contracts"].add(contract)
                stats["eligible"] += 1
                stats["up20"] += change >= 20
                stats["down20"] += change <= -20
                stats["sum_pct"] += change
    cohorts = []
    for (horizon, group), stats in sorted(groups.items()):
        count = stats["eligible"]
        cohorts.append({
            "horizon": horizon, "blocker": group, "observations": count,
            "sampled_up_20pct": stats["up20"], "sampled_down_20pct": stats["down20"],
            "mean_sampled_change_pct": round(stats["sum_pct"] / count, 2),
            "sufficient_for_review": count >= MIN_EVIDENCE,
            # Emerging patterns become visible after three comparable receipts,
            # without relaxing the evidence threshold for strategy changes.
            "early_signal": (
                "possible_missed_upside" if 3 <= count < MIN_EVIDENCE
                and stats["up20"] >= 2 and stats["up20"] / count >= 0.6
                else "possible_downside_protection" if 3 <= count < MIN_EVIDENCE
                and stats["down20"] >= 2 and stats["down20"] / count >= 0.6
                else "insufficient_evidence"
            ),
            "action": "review_offline_only" if count >= MIN_EVIDENCE else "collect_more",
        })
    return {
        "version": "learning-feedback-r1",
        "at": now.isoformat(), "cohorts": cohorts, "excluded": dict(sorted(excluded.items())),
        "policy": "observe_and_evaluate_only",
        "auto_parameter_changes": False, "full_entry_eligibility_verified": False,
        "executable_fills_verified": False,
        "scope": "Prospective sampled receipt prices only; not executable PnL, causal effect, market freshness or authorization to trade. No parameter changes until separate out-of-sample PAPER validation."
    }

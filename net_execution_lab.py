"""V11 PAPER-only execution cost gate; pure calculations, no orders or wallet writes."""
import math

def assess_net_entry(budget_eur, expected_move_pct, fee_per_side=0.01,
                     slippage_per_side=0.02, extra_exit_impact_pct=0.0,
                     minimum_net_pct=0.0, liquidity_eur=None,
                     max_position_liquidity_pct=0.01):
    """Conservative scenario, not a prediction or an executable quote.

    Percent fields are expressed in percentage points; fee/slippage as fractions.
    Missing/non-finite evidence rejects rather than inventing a price.
    """
    numbers = (budget_eur, expected_move_pct, fee_per_side, slippage_per_side,
               extra_exit_impact_pct, minimum_net_pct, max_position_liquidity_pct)
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in numbers):
        return {"allowed": False, "reason": "invalid_or_missing_inputs", "net_pct": None}
    if budget_eur <= 0 or fee_per_side < 0 or slippage_per_side < 0 or extra_exit_impact_pct < 0 or max_position_liquidity_pct <= 0:
        return {"allowed": False, "reason": "invalid_cost_or_budget", "net_pct": None}
    if fee_per_side >= 1 or slippage_per_side >= 1 or extra_exit_impact_pct >= 100 or expected_move_pct <= -100:
        return {"allowed": False, "reason": "invalid_execution_scenario", "net_pct": None}
    if liquidity_eur is None or isinstance(liquidity_eur, bool) or not isinstance(liquidity_eur, (int, float)) or not math.isfinite(liquidity_eur) or liquidity_eur <= 0:
        return {"allowed": False, "reason": "liquidity_unverified", "net_pct": None}
    if budget_eur > liquidity_eur * max_position_liquidity_pct:
        return {"allowed": False, "reason": "position_too_large_for_liquidity", "net_pct": None}
    entry_units_factor = 1 / ((1 + fee_per_side) * (1 + slippage_per_side))
    exit_factor = (1 - fee_per_side) * (1 - slippage_per_side) * (1 - extra_exit_impact_pct / 100)
    net_pct = ((1 + expected_move_pct / 100) * entry_units_factor * exit_factor - 1) * 100
    return {"allowed": net_pct >= minimum_net_pct, "reason": "passes_net_scenario" if net_pct >= minimum_net_pct else "insufficient_net_edge",
            "net_pct": round(net_pct, 4), "net_eur": round(budget_eur * net_pct / 100, 4),
            "version": "v11-paper-net-r1", "execution_verified": False}

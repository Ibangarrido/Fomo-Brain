"""Prospective observations, never a wallet or reconstructed trading return."""
import json
import math
import os
from datetime import datetime, timezone, timedelta

FILE = "fomo_opportunity_audit_r1.json"
LIMIT = 500
REJECTED_RESERVE = 100
MANUAL_RESERVE = 32
HORIZON_SECONDS = 72 * 3600
MAX_TRACKING_SECONDS = HORIZON_SECONDS + 24 * 3600
MANUAL = {
    # NETWORK: user-provided video, post-event observation only.
    ("solana", "8THZ69JP2ErZuHVj4G5rcwkFfsQafp5mQsaoQReApump"),
    # WHITEWHALE: user-supplied 2026-10-25 video; research-only after the observed move.
    ("solana", "AXoNsSQ2DjoBY8x8fP76pCeqrjhZEFRmRnnaM5hegVQx"),
    ("solana", "EcZndAERfzNhLirHwfsy44dAyPSZazjDU83pa6RApump"),
    ("solana", "HwJyyniKKDRLXxjRSzyLtpvxzqecqrhrbcSbKRm7STNK"),
    ("solana", "64oAuE88tNP7KsSyaiJTKGP4sWmLMFGWLUs9eBTLYgCp"),
    ("solana", "EkFRff9a2jKztJHML1LG9FRmEkPJDR6XAYp3uCPdpump"),
    ("solana", "4mbPZzDCWXvTCJbscMWeDD7TT1pra9mkZHGaBxc2jupx"),
}
RESEARCH_TARGETS = {
    ("solana", "2bCCHQadi4QeHWPKG3w13siCyWWQPgkFtniouTqVpump"),
    ("bsc", "0x8175810d00f9356a8f87a4a7b8ff7660087c7777"),
    ("solana", "GtcZuRzgp8U4qCkF2sBeihrnTsfYUrQiJUs3E81pump"),
    ("robinhood", "0xb0f444a069d9264017610e0674ebf7e1d6e19cbb"),
    ("bsc", "0x7aede49f29bf7bc643853c1136854ea8e4da7777"),
    ("solana", "EaqXJVr1aFPhMyTJbDCpwvTeiKc8x4gueFjFKKBvtcWY"),
}
MANUAL |= RESEARCH_TARGETS

DECISIONS = {}


def same_contract(chain, a, b):
    return a == b if chain == "solana" else str(a).lower() == str(b).lower()


def is_manual(chain, address):
    return any(c == chain and same_contract(chain, address, a) for c, a in MANUAL)


def entry_summary(candidate_count, notes):
    """First blocking reason per candidate; counts are not independent gates."""
    reasons = {}
    entered = omitted = rejected = 0
    for note in notes:
        if note.startswith("ENTRADA VIRTUAL "):
            entered += 1
        elif note.startswith("ENTRADA OMITIDA "):
            omitted += 1
        elif note.startswith("DESCARTE ") and " | " in note:
            rejected += 1
            reason = note.split(" | ", 1)[1].split(" | ", 1)[0][:240]
            reasons[reason] = reasons.get(reason, 0) + 1
    ordered = sorted(reasons.items(), key=lambda item: (-item[1], item[0]))
    return {"version": "entry-audit-r1", "candidates": candidate_count,
            "entered": entered, "rejected": rejected, "omitted": omitted,
            "top_first_blockers": dict(ordered[:10]),
            "other_rejections": sum(count for _, count in ordered[10:]),
            "scope": "first blocking reason per candidate; virtual entries only"}


def begin_cycle():
    DECISIONS.clear()


def record_decisions(label, notes):
    for note in notes:
        if note.startswith("DESCARTE ") and " | " in note:
            key, reason = note[9:].split(" | ", 1)
            DECISIONS.setdefault(key, {})[label] = reason


def read():
    if not os.path.exists(FILE):
        return {"version": 1, "tokens": {}, "capacity_skips": 0}
    with open(FILE) as handle:
        state = json.load(handle)
    if state.get("version") != 1 or not isinstance(state.get("tokens"), dict):
        raise ValueError("Auditoria incompatible; conservar archivo, no reiniciar")
    return state


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def retire_finished(state, now):
    """Keep active study cases; retain only IDs and counts for finished cases."""
    finished = state.setdefault('finished_tokens', {})
    if not isinstance(finished, dict):
        raise ValueError('Resumen de oportunidades incompatible; no reiniciar')
    totals = state.setdefault('retired_counts', {'horizon_observed': 0, 'horizon_unknown': 0})
    for key, row in list(state['tokens'].items()):
        if is_manual(row['chain'], row['address']):
            continue
        age = (now - datetime.fromisoformat(row['first']['received_at'])).total_seconds()
        if not row.get('complete') and age < MAX_TRACKING_SECONDS:
            continue
        # Minimal IDs prevent restarting the same prospective cohort. No price
        # history, balances or supposed final price are copied into this summary.
        reason = 'horizon_observed' if row.get('complete') else 'horizon_unknown'
        if key not in finished:
            finished[key] = {'retired_at': now.isoformat(), 'reason': reason}
            totals[reason] += 1
        del state['tokens'][key]
    return finished


def market_screen(snapshot, age_minutes, max_age):
    """Independent EARLY market gates, not full eligibility or a buy signal."""
    checks = [
        (snapshot["liquidity"], lambda v: v >= 20000, "liquidity_20000"),
        (snapshot["buy_ratio5m"], lambda v: v >= .60, "buy_count_60pct"),
        (snapshot["trades5m"], lambda v: v >= 40, "trades5m_40"),
        (snapshot["change5m"], lambda v: 2 <= v <= 60, "momentum5m_2_60"),
        (snapshot["change1h"], lambda v: v <= 150, "change1h_max150"),
        (age_minutes, lambda v: 2 <= v <= max_age, "pair_age_2_" + str(max_age)),
    ]
    return {name: "UNKNOWN" if value is None else "PASS" if predicate(value) else "FAIL"
            for value, predicate, name in checks}


def early_discovery_screen(snapshot, age_minutes):
    """Research-only pre-spike alert; NEVER a buy signal or eligibility override."""
    checks = [
        (snapshot["liquidity"], lambda v: v >= 20000, "liquidity_20000"),
        (snapshot["trades5m"], lambda v: v >= 40, "trades5m_40"),
        (snapshot["change5m"], lambda v: 2 <= v <= 60, "momentum5m_2_60"),
        (age_minutes, lambda v: 2 <= v <= 60, "pair_age_2_60"),
    ]
    gates = {name: "UNKNOWN" if value is None else "PASS" if predicate(value)
             else "FAIL" for value, predicate, name in checks}
    # Deliberately track rather than waive these two safety constraints.
    gates["buy_ratio_60pct"] = ("UNKNOWN" if snapshot["buy_ratio5m"] is None
                               else "PASS" if snapshot["buy_ratio5m"] >= .60 else "FAIL")
    gates["change1h_max150"] = ("UNKNOWN" if snapshot["change1h"] is None
                                else "PASS" if snapshot["change1h"] <= 150 else "FAIL")
    return {"research_candidate": all(gates[k] == "PASS" for k in
            ("liquidity_20000", "trades5m_40", "momentum5m_2_60", "pair_age_2_60")),
            "checks": gates, "entry_authorized": False}


def watch_targets(now=None):
    now = now or datetime.now(timezone.utc)
    state = read()
    active = []
    for row in state["tokens"].values():
        age = (now - datetime.fromisoformat(row["first"]["received_at"])).total_seconds()
        if 0 <= age < HORIZON_SECONDS + 24 * 3600 and not row.get("complete"):
            active.append(row)
    # Prioritize a pending rejection checkpoint only during its actual
    # 0..120s sampling window. Do not chase overdue cases indefinitely.
    # This changes RESEARCH requests only, never entry or exit decisions.
    def checkpoint_deadline(row):
        baseline = row.get("first_rejection")
        if not baseline:
            return None
        try:
            rejected_at = datetime.fromisoformat(baseline["received_at"])
        except (KeyError, TypeError, ValueError):
            return None
        pending = row.get("post_rejection_checkpoints", {})
        deadlines = []
        for minutes in (5, 15, 30, 60):
            if str(minutes) + "m" in pending:
                continue
            due = rejected_at + timedelta(minutes=minutes)
            seconds_after_due = (now - due).total_seconds()
            if -60 <= seconds_after_due <= 120:
                # Prewarm during the minute BEFORE the checkpoint so the next
                # scheduled observation is less likely to miss the 120s window.
                deadlines.append(abs(seconds_after_due))
        return min(deadlines) if deadlines else None

    # Keep existing per-pool quotas and full-stride rotation for non-urgent
    # watches. Priority is chronological, never based on price performance.
    def rotate(rows, count):
        targets = sorted((r["chain"], r["address"]) for r in rows)
        start = state.get("watch_cursor", 0) % len(targets) if targets else 0
        rotated = targets[start:] + targets[:start]
        urgent = sorted(
            ((deadline, r["chain"], r["address"]) for r in rows
             if (deadline := checkpoint_deadline(r)) is not None))
        prioritized = [(chain, address) for _, chain, address in urgent]
        priority_set = set(prioritized)
        return (prioritized + [target for target in rotated
                               if target not in priority_set])[:count]
    automatic = [r for r in active if not is_manual(r["chain"], r["address"])]
    rejected = [r for r in automatic if r.get("admission_pool") == "rejected_reserve"]
    ordinary = [r for r in automatic if r.get("admission_pool") != "rejected_reserve"]
    # Same ten automatic requests; reserve five for each cohort when both exist.
    selected = rotate(rejected, 5 if ordinary else 10)
    selected += rotate(ordinary, 10 - len(selected))
    if len(selected) < 10:
        selected += [t for t in rotate(rejected, 10) if t not in selected][:10-len(selected)]
    due_targets = {(r["chain"], r["address"]) for r in automatic
                   if checkpoint_deadline(r) is not None}
    if due_targets:
        print("WATCH CHECKPOINT PRIORITY " + json.dumps({
            "due_or_prewarms": len(due_targets),
            "selected_due": len(due_targets.intersection(selected)),
            "automatic_requests": len(selected),
            "scope": "research quote requests only; provider freshness and fills unverified"}))
    return sorted(MANUAL) + selected



def research_watches(state, selected, now, fetch_context=None):
    """Bounded candle research independent of ranking and entry rejections."""
    targets = sorted(RESEARCH_TARGETS)
    quoted = {}
    for chain, address in targets:
        matches = [p for p in selected.values() if p.get("chainId") == chain
                   and same_contract(chain, (p.get("baseToken") or {}).get("address"), address)]
        if matches:
            quoted[chain + ":" + address] = max(matches, key=lambda p: number((p.get("liquidity") or {}).get("usd")) or 0)
    coverage = [{"chain": chain, "address": address,
                 "status": "RECEIVED" if chain + ":" + address in quoted else "NO_QUOTE_THIS_CYCLE"}
                for chain, address in targets]
    state["research_watch_coverage"] = {"at": now.isoformat(), "targets": coverage,
                                      "scope": "response coverage; not provider market freshness"}
    print("WATCH COVERAGE " + json.dumps(state["research_watch_coverage"]))
    if fetch_context is None:
        if os.getenv("BRAIN_CANDLE_LAB", "0") != "1":
            return
        from candle_lab import context
        fetch_context = context
    minute = int(now.timestamp() // 60)
    if state.get("research_watch_minute", -1) >= minute:
        return
    state["research_watch_minute"] = minute
    cursor = state.get("research_watch_cursor", 0)
    chain, address = targets[cursor % len(targets)]
    state["research_watch_cursor"] = cursor + 1
    key = chain + ":" + address
    pair = quoted.get(key)
    record = {"at": now.isoformat(), "chain": chain, "address": address,
              "execution_verified": False, "changes_orders": False,
              "buy_volume_usd": None, "sell_volume_usd": None,
              "flow_by_amount": "UNKNOWN: source supplies total volume and transaction counts only"}
    if pair is None:
        record["context"] = {"status": "SIN DATOS", "reason": "sin cotizacion del contrato en este ciclo"}
    else:
        token = {"chain": chain, "address": address, "pair": pair["pairAddress"]}
        try:
            record["context"] = fetch_context(token, now=now.timestamp())
        except Exception as exc:
            record["context"] = {"status": "SIN DATOS", "reason": type(exc).__name__}
        tx = (pair.get("txns") or {}).get("m5") or {}
        buys, sells = number(tx.get("buys")), number(tx.get("sells"))
        ratio = buys / (buys + sells) if (buys is not None and sells is not None
                                        and buys >= 0 and sells >= 0 and buys + sells > 0) else None
        record["buy_count_ratio5m"] = ratio
        record["count_thresholds"] = {str(t): "UNKNOWN" if ratio is None else
                                     "PASS" if ratio >= t / 100 else "FAIL"
                                     for t in (50, 60, 75)}
        record["threshold_scope"] = "one count-ratio gate only; not full entry eligibility"
        record["pair"] = pair["pairAddress"]
    state["research_watch_history"] = (state.get("research_watch_history", []) + [record])[-120:]
    print("WATCH PATTERN " + json.dumps(record, allow_nan=False))


def observe(pairs, sources, now=None, discovery_rejections=()):
    now = now or datetime.now(timezone.utc)
    state = read()
    finished = retire_finished(state, now)
    rows = state["tokens"]
    selected = {}
    fresh_observations_accepted = 0
    cached_or_replayed_receipts = 0
    for pair in pairs.values():
        chain = pair.get("chainId")
        address = (pair.get("baseToken") or {}).get("address")
        price = number(pair.get("priceUsd"))
        liquidity = number((pair.get("liquidity") or {}).get("usd"))
        if not chain or not address or not pair.get("pairAddress") or price is None or price <= 0:
            continue
        key = chain + ":" + address
        # One prospective cohort per contract; a finished case cannot restart
        # with a favourable new baseline or occupy a monitoring slot again.
        if key in finished:
            continue
        old = selected.get(key)
        if old is None or (liquidity or 0) > (number((old.get("liquidity") or {}).get("usd")) or 0):
            selected[key] = pair
    # Fixed ordering, independent of later performance or the ranking score.
    for key, pair in sorted(selected.items()):
        chain, address = pair["chainId"], pair["baseToken"]["address"]
        liquidity = number((pair.get("liquidity") or {}).get("usd"))
        cap = number(pair.get("marketCap") or pair.get("fdv"))
        manual = is_manual(chain, address)
        if key not in rows:
            if not manual and not (liquidity is not None and liquidity >= 10000
                                   and cap is not None and 0 < cap <= 2000000):
                continue
            if manual:
                pool, limit = "manual_reserve", MANUAL_RESERVE
            else:
                normal_count = sum(not is_manual(r["chain"], r["address"])
                                   and r.get("admission_pool", "automatic") == "automatic"
                                   for r in rows.values())
                pool, limit = (("rejected_reserve", REJECTED_RESERVE)
                               if normal_count >= LIMIT and DECISIONS.get(key)
                               else ("automatic", LIMIT))
            count = sum(("manual_reserve" if is_manual(r["chain"], r["address"])
                         else r.get("admission_pool", "automatic")) == pool
                        for r in rows.values())
            if count >= limit:
                state["capacity_skips"] += 1
                skips = state.setdefault("capacity_skips_by_pool", {})
                skips[pool] = skips.get(pool, 0) + 1
                continue
        else:
            pool = rows[key].get("admission_pool", "automatic")
        m5 = (pair.get("txns") or {}).get("m5") or {}
        buys, sells = number(m5.get("buys")), number(m5.get("sells"))
        # Cached responses retain their receipt time. Evaluation cannot rejuvenate them.
        try:
            received = datetime.fromisoformat(pair.get("_brain_received_at") or now.isoformat())
            if received.tzinfo is None or received > now:
                raise ValueError("invalid receipt")
        except (ValueError, TypeError):
            state["invalid_receipt_skips"] = state.get("invalid_receipt_skips", 0) + 1
            continue
        if key in rows and received <= datetime.fromisoformat(rows[key]["last"]["received_at"]):
            cached_or_replayed_receipts += 1
            continue
        created = number(pair.get("pairCreatedAt"))
        age_minutes = (received.timestamp() - created / 1000) / 60 if created is not None and created > 0 else None
        snapshot = {"received_at": received.isoformat(), "evaluated_at": now.isoformat(), "price": number(pair["priceUsd"]),
                    "pair": pair["pairAddress"], "market_cap": cap, "liquidity": liquidity,
                    "buys5m": buys, "sells5m": sells,
                    "trades5m": buys + sells if buys is not None and sells is not None else None,
                    "pair_age_minutes": age_minutes,
                    "buy_ratio5m": buys / (buys + sells) if buys is not None and sells is not None and buys + sells > 0 else None,
                    "change5m": number((pair.get("priceChange") or {}).get("m5")),
                    "change1h": number((pair.get("priceChange") or {}).get("h1")),
                    "sources": sorted(sources.get((chain, pair["pairAddress"]), [])),
                    "entry_rejections": dict(DECISIONS.get(key, {})),
                    "discovery_rejections": sorted({r["reason"] for r in discovery_rejections
                        if r.get("chain") == chain and r.get("address") == address
                        and r.get("pair") == pair["pairAddress"]}),
                    "data_freshness": "UNKNOWN", "execution_verified": False,
                    # DexScreener m5 buys/sells count transactions, NOT distinct wallets.
                    # No whale attribution or smart-money confirmation is possible here.
                    "whale_flow": {"status": "UNVERIFIED", "unique_buyers": None,
                                   "unique_sellers": None, "smart_money_net_usd": None,
                                   "cluster_independence_verified": False,
                                   "source": "not_available_in_pair_snapshot"}}
        snapshot["early_market_screens"] = {str(age): market_screen(snapshot, age_minutes, age)
                                            for age in (60, 1440)}
        snapshot["pre_spike_research"] = early_discovery_screen(snapshot, age_minutes)
        snapshot["screen_scope"] = "Independent market gates only; excludes score, wallet risk, security, confirmation and executable quotes; not entry eligibility."
        if key not in rows:
            rows[key] = {"chain": chain, "address": address,
                         "symbol": pair["baseToken"].get("symbol"),
                         "cohort": ("manual_after_event" if manual else
                                    "automatic_rejected_overflow" if pool == "rejected_reserve"
                                    else "automatic_prospective"),
                         "admission_pool": pool,
                         "first": snapshot, "last": snapshot, "peak": snapshot,
                         "observations": 0, "pair_changes": 0, "max_observation_gap_seconds": 0,
                         "trough": snapshot, "post_rejection_checkpoints": {}}
        row = rows[key]
        if row.get("complete"):
            continue
        gap = (received - datetime.fromisoformat(row["last"]["received_at"])).total_seconds()
        if gap < 0:
            raise ValueError("Observaciones fuera de orden; no sobrescribir")
        row["max_observation_gap_seconds"] = max(row["max_observation_gap_seconds"], gap)
        row["pair_changes"] += snapshot["pair"] != row["last"]["pair"]
        row["last"] = snapshot
        row["observations"] += 1
        fresh_observations_accepted += 1
        if snapshot["price"] > row["peak"]["price"]:
            row["peak"] = snapshot
        # Prospective sampled outcomes only; never claim an intrabar high or exact fill.
        # Legacy cohorts may lack trough; start from their first observed quote.
        row.setdefault("trough", row["first"])
        if snapshot["price"] < row["trough"]["price"]:
            row["trough"] = snapshot
        # Anchor the study to the FIRST ACTUAL REJECTION, not first discovery.
        # Older cohorts without a rejection anchor start prospectively at the
        # first observed rejection; no past performance is reconstructed.
        rejected = bool(snapshot["entry_rejections"] or snapshot["discovery_rejections"])
        if rejected and "first_rejection" not in row:
            row["first_rejection"] = snapshot
            row["rejection_peak"] = snapshot
            row["rejection_trough"] = snapshot
        baseline = row.get("first_rejection")
        if baseline and received >= datetime.fromisoformat(baseline["received_at"]):
            row.setdefault("rejection_peak", baseline)
            row.setdefault("rejection_trough", baseline)
            if snapshot["price"] > row["rejection_peak"]["price"]:
                row["rejection_peak"] = snapshot
            if snapshot["price"] < row["rejection_trough"]["price"]:
                row["rejection_trough"] = snapshot
            checkpoints = row.setdefault("post_rejection_checkpoints", {})
            elapsed_seconds = (received - datetime.fromisoformat(baseline["received_at"])).total_seconds()
            for minutes in (5, 15, 30, 60):
                name = str(minutes) + "m"
                if name not in checkpoints and elapsed_seconds >= minutes * 60:
                    checkpoints[name] = {
                        "target_at": (datetime.fromisoformat(baseline["received_at"])
                                      + timedelta(minutes=minutes)).isoformat(),
                        "observed_at": received.isoformat(),
                        "lag_seconds": elapsed_seconds - minutes * 60,
                        "price_change_pct": (snapshot["price"] / baseline["price"] - 1) * 100,
                        "sampled_peak_pct": (row["rejection_peak"]["price"] / baseline["price"] - 1) * 100,
                        "sampled_trough_pct": (row["rejection_trough"]["price"] / baseline["price"] - 1) * 100,
                        "pair_changed": snapshot["pair"] != baseline["pair"],
                        "exact_horizon": elapsed_seconds == minutes * 60,
                        "execution_verified": False,
                        "sampled_up_20pct": (row["rejection_peak"]["price"] / baseline["price"] - 1) >= 0.20,
                        "sampled_down_20pct": (row["rejection_trough"]["price"] / baseline["price"] - 1) <= -0.20,
                        "entry_rejection_reasons": dict(baseline["entry_rejections"]),
                        "discovery_rejection_reasons": list(baseline["discovery_rejections"])}
        # Research-only second-look screen: compare the current receipt with the
        # first rejected snapshot. This never authorizes a simulated order.
        if baseline and received > datetime.fromisoformat(baseline["received_at"]):
            checks = market_screen(snapshot, age_minutes, 60)
            history = row.setdefault("second_look_history", [])
            history.append({
                "observed_at": received.isoformat(),
                "minutes_since_rejection": round((received - datetime.fromisoformat(
                    baseline["received_at"])).total_seconds() / 60, 2),
                "checks": checks,
                "market_gates_pass": all(value == "PASS" for value in checks.values()),
                "buy_ratio_delta": (snapshot["buy_ratio5m"] - baseline["buy_ratio5m"]
                                    if snapshot["buy_ratio5m"] is not None
                                    and baseline["buy_ratio5m"] is not None else None),
                "liquidity_change_pct": ((snapshot["liquidity"] / baseline["liquidity"] - 1) * 100
                                         if snapshot["liquidity"] is not None
                                         and baseline["liquidity"] is not None
                                         and baseline["liquidity"] > 0 else None),
                "pair_changed": snapshot["pair"] != baseline["pair"],
                "two_bullish_candles": "UNKNOWN",
                "executable_quote": "UNKNOWN",
                "entry_authorized": False,
            })
            del history[:-16]
        row["observed_price_change_pct"] = (snapshot["price"] / row["first"]["price"] - 1) * 100
        row["observed_peak_change_pct"] = (row["peak"]["price"] / row["first"]["price"] - 1) * 100
        row["observed_drawdown_from_peak_pct"] = (snapshot["price"] / row["peak"]["price"] - 1) * 100
        elapsed = (received - datetime.fromisoformat(row["first"]["received_at"])).total_seconds()
        if elapsed >= HORIZON_SECONDS:
            row["complete"] = True
            row["completion"] = "first received observation after 72h; not exact horizon price"
    research_watches(state, selected, now)
    state.setdefault("coverage_policy_history", [])
    if not state["coverage_policy_history"] or state["coverage_policy_history"][-1]["version"] != "coverage-r2":
        state["coverage_policy_history"].append({"version": "coverage-r2", "effective_at": now.isoformat(),
            "automatic_limit": LIMIT, "rejected_reserve": REJECTED_RESERVE,
            "manual_reserve": MANUAL_RESERVE, "automatic_watch_requests": 10,
            "scope": "coverage and receipt timing only; no entry-policy change"})
    # Audit sampling coverage separately from pair presence. A token in the
    # incoming selected set may carry an unchanged cached receipt, so the old
    # observed_this_cycle count is NOT a count of fresh observations.
    checkpoint_coverage = {}
    for minutes in (5, 15, 30, 60):
        name = str(minutes) + "m"
        counts = {"due": 0, "on_time_within_120s": 0,
                  "late_over_120s": 0, "missing": 0, "not_due": 0,
                  "on_time_sampled_up_20pct": 0,
                  "on_time_sampled_down_20pct": 0,
                  "on_time_pair_changed": 0}
        for row in rows.values():
            baseline = row.get("first_rejection")
            if not baseline:
                continue
            try:
                due_at = datetime.fromisoformat(baseline["received_at"]) + timedelta(minutes=minutes)
            except (KeyError, ValueError, TypeError):
                continue
            if now < due_at:
                counts["not_due"] += 1
                continue
            counts["due"] += 1
            checkpoint = row.get("post_rejection_checkpoints", {}).get(name)
            if checkpoint is None:
                counts["missing"] += 1
            elif checkpoint.get("lag_seconds") is not None and 0 <= checkpoint["lag_seconds"] <= 120:
                counts["on_time_within_120s"] += 1
                # Only timely sampled observations can support horizon-specific
                # outcomes. Late snapshots cannot establish a 5/15/30/60m move.
                counts["on_time_sampled_up_20pct"] += bool(checkpoint.get("sampled_up_20pct"))
                counts["on_time_sampled_down_20pct"] += bool(checkpoint.get("sampled_down_20pct"))
                counts["on_time_pair_changed"] += bool(checkpoint.get("pair_changed"))
            else:
                counts["late_over_120s"] += 1
        checkpoint_coverage[name] = counts
    state["last_cycle_coverage"] = {
        "at": now.isoformat(),
        "selected_existing_rows": sum(k in selected for k in rows),
        "fresh_observations_accepted": fresh_observations_accepted,
        "cached_or_replayed_receipts": cached_or_replayed_receipts,
        "checkpoint_coverage": checkpoint_coverage,
        "scope": "Receipt-time sampling only; provider market freshness unknown. Timely sampled moves are NOT candle highs, executable fills, or trading returns; late/missing checkpoints are excluded from horizon outcomes."}
    state["last_cycle_at"] = now.isoformat()
    # Advance by the number of automatic slots actually allocated per pool.
    # A stride of one revisits almost the same ten contracts every cycle,
    # leaving most rejection checkpoints unobserved.
    active_auto = [r for r in rows.values()
                   if not is_manual(r["chain"], r["address"]) and not r.get("complete")]
    has_rejected = any(r.get("admission_pool") == "rejected_reserve" for r in active_auto)
    has_ordinary = any(r.get("admission_pool") != "rejected_reserve" for r in active_auto)
    state["watch_cursor"] = state.get("watch_cursor", 0) + (
        5 if has_rejected and has_ordinary else 10)
    state["limitations"] = "Received market snapshots; freshness unknown; sampled peaks; gaps and pair changes recorded; no trades, costs or net return. Manual cases excluded from automatic cohort. Missing quotes never become zero. Active capacity bounded; skips counted. Completed or 96h-unresolved automatic cases removed from active tracking; only IDs and aggregate completion counts retained; no fabricated final prices."
    with open(FILE + ".tmp", "w") as handle:
        json.dump(state, handle, indent=2, allow_nan=False)
    os.replace(FILE + ".tmp", FILE)
    print("AUDITORIA OPORTUNIDADES " + json.dumps({"tracked": len(rows), "capacity_skips": state["capacity_skips"],
          "retired": len(state['finished_tokens']),
          "capacity_skips_by_pool": state.get("capacity_skips_by_pool", {}),
          "observed_this_cycle": sum(k in selected for k in rows),
          "fresh_observations_accepted": fresh_observations_accepted,
          "cached_or_replayed_receipts": cached_or_replayed_receipts,
          "checkpoint_coverage": checkpoint_coverage,
          "market_freshness_verified": False,
          "no_trading_return": True}))
    # Surface a bounded, auditable leaderboard in Actions logs. These are
    # sampled price observations, never exact candle highs or executable P&L.
    rejected_auto = []
    for row in rows.values():
        if row.get("cohort") == "manual_after_event":
            continue
        baseline = row.get("first_rejection")
        peak = row.get("rejection_peak")
        if not baseline or not peak or not baseline.get("price"):
            continue
        peak_pct = (peak["price"] / baseline["price"] - 1) * 100
        rejected_auto.append({
            "chain": row["chain"], "address": row["address"],
            "symbol": row.get("symbol"),
            "rejected_at": baseline["received_at"],
            "peak_observed_at": peak["received_at"],
            "sampled_peak_after_rejection_pct": round(peak_pct, 2),
            "rejection_reasons": baseline.get("entry_rejections", {}),
            "discovery_reasons": baseline.get("discovery_rejections", []),
            "observations": row.get("observations", 0),
            "max_gap_seconds": row.get("max_observation_gap_seconds"),
            "pair_changes": row.get("pair_changes", 0),
            "execution_verified": False})
    rejected_auto.sort(key=lambda x: x["sampled_peak_after_rejection_pct"], reverse=True)
    print("DESCARTES PICOS MUESTREADOS " + json.dumps({
        "eligible_rows_with_rejection_anchor": len(rejected_auto),
        "sampled_up_20pct": sum(x["sampled_peak_after_rejection_pct"] >= 20 for x in rejected_auto),
        "top_10": rejected_auto[:10],
        "scope": "automatic cohort, sampled observations only; not exact highs or trade profits"
    }, allow_nan=False))
    for chain, address in sorted(MANUAL):
        row = rows.get(chain + ":" + address)
        if row:
            print("ESTUDIO OPORTUNIDAD " + json.dumps({k: row[k] for k in ("chain", "address", "symbol", "cohort", "first", "last", "observed_price_change_pct", "observed_peak_change_pct", "observed_drawdown_from_peak_pct")}, allow_nan=False))




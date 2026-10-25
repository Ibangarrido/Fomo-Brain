"""Prospective PAPER diagnostics. No orders, no wallet mutations, no policy overrides."""
import json
import math
import os
import time
from datetime import datetime, timezone, timedelta
from paper_observability import net_paper_exit

FILE = 'fomo_v12_observations_r1.json'
REPORT = 'paper_observability_status.json'
WALLETS = {'CONTROL': 'fomo_lab_v11_control_r1.json', 'NET': 'fomo_lab_v11_net_r1.json'}
LABELS = {'V11 CONTROL 100 EUR': 'CONTROL', 'V11 NET 100 EUR': 'NET'}
HORIZONS = (5, 15, 30, 60)
MAX_CASES = 500
MAX_QUOTES = 20


def instant(value):
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.utcoffset() is None:
        raise ValueError('Timezone-aware timestamp required')
    return result


def number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def positive(value):
    n = number(value)
    return n if n is not None and n > 0 else None


def read(path=FILE):
    if not os.path.exists(path):
        return {'version': 'v12-r1', 'cases': [], 'evaluations': {}, 'capacity_skips': 0,
                'invalid_references': 0, 'retired': {str(h): {'observed': 0, 'unknown': 0} for h in HORIZONS}}
    with open(path) as handle:
        state = json.load(handle)
    if state.get('version') != 'v12-r1' or not isinstance(state.get('cases'), list):
        raise ValueError('V12 state incompatible; refusing to reset history')
    return state


def save(state, path=FILE):
    with open(path + '.tmp', 'w') as handle:
        json.dump(state, handle, indent=2, allow_nan=False)
    os.replace(path + '.tmp', path)


def identity(token):
    key = tuple(token.get(k) for k in ('chain', 'address', 'pair'))
    if not all(isinstance(k, str) and k for k in key):
        raise ValueError('Exact chain, contract and pair required')
    return key


def register_rejections(state, label, ranking, notes, now):
    """One prospective case per arm/pair per hour; count repeated decisions separately."""
    instant(now)
    arm = LABELS[label]
    tokens = {t['chain'] + ':' + t['address']: t for t in ranking}
    stats = state['evaluations'].setdefault(arm, {'rejected': 0, 'first_blockers': {}})
    for note in notes:
        if not note.startswith('DESCARTE ') or ' | ' not in note:
            continue
        key, reason = note[len('DESCARTE '):].split(' | ', 1)
        reason = reason.split(' | ', 1)[0][:240]
        token = tokens.get(key)
        if token is None:
            continue
        stats['rejected'] += 1
        stats['first_blockers'][reason] = stats['first_blockers'].get(reason, 0) + 1
        try:
            ident = identity(token)
            receipt = instant(token.get('received_at'))
            price = positive(token.get('price'))
            if price is None or not 0 <= (now - receipt).total_seconds() <= 90:
                raise ValueError('Missing or old reference receipt')
        except (ValueError, TypeError):
            state['invalid_references'] += 1
            continue
        if any(c['arm'] == arm and identity(c) == ident and
               (now - instant(c['rejected_at'])).total_seconds() < 3720 for c in state['cases']):
            continue
        if len(state['cases']) >= MAX_CASES:
            state['capacity_skips'] += 1
            continue
        state['cases'].append(dict(zip(('chain', 'address', 'pair'), ident), arm=arm,
            symbol=token.get('symbol'), reason=reason, rejected_at=now.isoformat(),
            reference_price=price, reference_received_at=receipt.isoformat(),
            source_market_age_seconds=None, execution_verified=False, horizons={}))


def pending(case, now):
    age = (now - instant(case['rejected_at'])).total_seconds()
    return [h for h in HORIZONS if str(h) not in case['horizons'] and h * 60 <= age <= h * 60 + 120]


def refresh(state, quote, now, clock=None):
    """Quote only due cases, bounded and deduplicated. Receipt is not trade freshness."""
    due = {}
    for case in state['cases']:
        age = (now - instant(case['rejected_at'])).total_seconds()
        for h in HORIZONS:
            if str(h) not in case['horizons'] and age > h * 60 + 120:
                case['horizons'][str(h)] = {'status': 'unknown', 'reason': 'no_quote_in_window', 'return_pct': None}
        if pending(case, now):
            due.setdefault(identity(case), []).append(case)
    # Earliest deadline first; keep deterministic ordering independent of returns.
    targets = sorted(due, key=lambda key: min(
        instant(c['rejected_at']).timestamp() + min(pending(c, now)) * 60 + 120 for c in due[key]))[:MAX_QUOTES]
    deadline = time.monotonic() + 10
    requested = 0
    for key in targets:
        if time.monotonic() >= deadline:
            break
        requested += 1
        cases = due[key]
        try:
            sample = quote(dict(zip(('chain', 'address', 'pair'), key)))
            checked_at = clock() if clock is not None else now
            receipt = instant(sample.get('received_at'))
            price = positive(sample.get('price'))
            if identity(sample) != key or price is None or not 0 <= (checked_at - receipt).total_seconds() <= 30:
                raise ValueError('Wrong identity or stale quote receipt')
        except Exception as exc:
            for case in cases:
                case['last_quote_error'] = str(exc)[:240]
            continue
        for case in cases:
            for h in pending(case, checked_at):
                target = instant(case['rejected_at']) + timedelta(minutes=h)
                if not target <= receipt <= target + timedelta(seconds=120):
                    continue
                case['horizons'][str(h)] = {'status': 'observed', 'received_at': receipt.isoformat(),
                    'price': price, 'return_pct': round((price / case['reference_price'] - 1) * 100, 6),
                    'source_market_age_seconds': None, 'execution_verified': False}
    # Retain completed cases for 24h, then aggregate counts; never restart them in the same horizon.
    keep = []
    for case in state['cases']:
        if len(case['horizons']) == len(HORIZONS) and (now - instant(case['rejected_at'])).total_seconds() > 86400:
            for h, result in case['horizons'].items():
                state['retired'][h][result['status']] += 1
        else:
            keep.append(case)
    state['cases'] = keep
    return {'due_pairs': len(due), 'requested_pairs': requested}


def record_cycle(label, ranking, notes, now=None):
    state = read()
    register_rejections(state, label, ranking, notes, now or datetime.now(timezone.utc))
    save(state)


def wallet_outcomes(wallet):
    """Reconcile partial/full sale legs with the wallet's actual cost allocation."""
    legs = []
    for sale in wallet.get('closed', []):
        qty, entry, exit_price = (positive(sale.get(k)) for k in ('sold_quantity', 'entry_price', 'exit_price'))
        allocated, proceeds, recorded = (number(sale.get(k)) for k in ('allocated_cost', 'proceeds', 'profit'))
        result = {'chain': sale.get('chain'), 'address': sale.get('address'), 'opened_at': sale.get('opened_at'),
                  'closed_at': sale.get('closed_at'), 'exit_reason': sale.get('exit_reason'),
                  'all_in_net_pnl_eur': None, 'execution_verified': False}
        if (None in (qty, entry, exit_price, allocated, proceeds, recorded) or allocated <= 0 or proceeds < 0):
            result.update(status='unknown', reason='missing_sale_evidence', modeled_net_pnl_eur=None)
        else:
            entry_cost = allocated - qty * entry
            exit_cost = qty * exit_price - proceeds
            pnl = net_paper_exit(qty, entry, exit_price, max(0, entry_cost), max(0, exit_cost), 0)
            valid = (entry_cost >= -1e-8 and exit_cost >= -1e-8 and
                     pnl['net_pnl'] is not None and math.isclose(pnl['net_pnl'], recorded, abs_tol=1e-6))
            result.update(status='modeled' if valid else 'unknown',
                reason='fixed_fx_gas_mev_unverified' if valid else 'cost_reconciliation_failed',
                modeled_net_pnl_eur=pnl['net_pnl'] if valid else None,
                gross_price_pnl_eur=qty * (exit_price - entry),
                modeled_entry_friction_eur=entry_cost, modeled_exit_friction_eur=exit_cost)
        legs.append(result)
    obs = (wallet.get('observations') or [{}])[-1]
    complete = (obs.get('valuation_complete') is True and obs.get('unverified_quotes') == 0
                and all(p.get('quote_status') == 'OK' for p in wallet.get('positions', [])))
    equity = number(obs.get('estimated_equity')) if complete else None
    unknown = sum(row['status'] == 'unknown' for row in legs)
    return {'cash_eur': number(wallet.get('cash')), 'reserve_eur': number(wallet.get('reserve')),
        'estimated_equity_eur': equity, 'valuation_complete': equity is not None,
        'as_of': obs.get('at'), 'open_positions': len(wallet.get('positions', [])),
        'unknown_positions': sum(p.get('quote_status') != 'OK' for p in wallet.get('positions', [])),
        'last_entry_audit': wallet.get('last_entry_audit'),
        'sale_legs': len(legs), 'unknown_sale_legs': unknown,
        'modeled_realized_net_pnl_eur': None if unknown else sum(row['modeled_net_pnl_eur'] for row in legs),
        'all_in_realized_net_pnl_eur': None if legs else 0.0,
        'model_currency': 'EUR with fixed USD/EUR=1; gas/MEV excluded', 'outcomes': legs}


def run_provenance(arms, now):
    """Report receipt freshness separately from valuation and execution evidence."""
    started = os.getenv('BRAIN_AUDIT_STARTED_AT')
    outcome = os.getenv('BRAIN_ENGINE_OUTCOME', 'unknown')
    for arm in arms.values():
        try:
            stamp = instant(arm.get('as_of'))
            age = (now - stamp).total_seconds()
            current = started is not None and instant(started) <= stamp <= now
        except (ValueError, TypeError):
            age, current = None, False
        arm['observation_age_seconds'] = age
        arm['updated_this_run'] = current if started else None
        arm['data_status'] = ('CURRENT_RUN' if current and outcome == 'success' else
                              'PARTIAL_RUN' if current else
                              'RESTORED_OR_NOT_UPDATED' if started else 'UNVERIFIED_RUN_CONTEXT')
    return {'run_id': os.getenv('GITHUB_RUN_ID'), 'run_attempt': os.getenv('GITHUB_RUN_ATTEMPT'),
            'event': os.getenv('GITHUB_EVENT_NAME'), 'commit_sha': os.getenv('GITHUB_SHA'),
            'audit_started_at': started, 'engine_outcome': outcome,
            'scheduled_cadence_verified': False}


def build_report(state, wallets, now):
    horizons = {}
    for h in HORIZONS:
        outcomes = [c['horizons'].get(str(h), {'status': 'pending'}) for c in state['cases']]
        returns = [r['return_pct'] for r in outcomes if r['status'] == 'observed']
        horizons[str(h)] = {'observed': len(returns), 'pending': sum(r['status'] == 'pending' for r in outcomes),
            'unknown': sum(r['status'] == 'unknown' for r in outcomes),
            'positive': sum(r > 0 for r in returns), 'negative': sum(r < 0 for r in returns),
            'mean_observed_return_pct': sum(returns) / len(returns) if returns else None}
    arms = {arm: wallet_outcomes(wallet) for arm, wallet in wallets.items()}
    provenance = run_provenance(arms, now)
    control, net = (arms.get(arm, {}).get('estimated_equity_eur') for arm in ('CONTROL', 'NET'))
    return {'version': 'v12-r1', 'generated_at': now.isoformat(), 'mode': 'paper_observability_only',
        'run_provenance': provenance,
        'forward_rejection_outcomes': 'integrated', 'net_execution_outcomes': 'integrated_modeled_only',
        'tracked_rejection_cases': len(state['cases']), 'evaluations': state['evaluations'],
        'invalid_references': state['invalid_references'], 'capacity_skips': state['capacity_skips'],
        'retired_horizons': state['retired'], 'forward_horizons_minutes': horizons, 'wallets': arms,
        'relative_modeled_equity_eur': net - control if None not in (net, control) else None,
        'scope': 'Rejected prices are prospective observations, not missed executable profits; repeated cases/arms are correlated.',
        'execution_verified': False, 'profitability_demonstrated': False,
        'source_market_freshness': 'UNKNOWN; receipt timestamps only',
        'coverage': '5/15/30/60m require a quote within +120s; gaps stay unknown; no monitoring between runs'}


def run(quote, now=None):
    now = now or datetime.now(timezone.utc)
    state = read()
    coverage = refresh(state, quote, now, clock=lambda: datetime.now(timezone.utc))
    save(state)
    report = write_report(now)
    print('V12 OBSERVABILITY ' + json.dumps(dict(coverage, tracked=report['tracked_rejection_cases'],
          horizons=report['forward_horizons_minutes']), allow_nan=False))
    return report


def write_report(now=None):
    wallets = {}
    for arm, path in WALLETS.items():
        with open(path) as handle:
            wallets[arm] = json.load(handle)
    report = build_report(read(), wallets, now or datetime.now(timezone.utc))
    save(report, REPORT)
    return report


if __name__ == '__main__':
    print(json.dumps(write_report(), indent=2, allow_nan=False))


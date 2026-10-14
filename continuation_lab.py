"""Prospective paper comparison; no signing or execution integration."""
import json
import os
from datetime import datetime, timezone
from exit_watchdog import wallet_fork
from m4_lab import write

MARKER = 'fomo_lab_continuation_start_r1.json'
ARMS = {
    'control': ('fomo_lab_continuation_control_r1.json', 'early', .75),
    '50': ('fomo_lab_continuation_50_r1.json', 'continuation', .50),
    '60': ('fomo_lab_continuation_60_r1.json', 'continuation', .60),
}
LEGACY_FILES = {item[0] for item in ARMS.values()}
PATTERN_MARKER = 'fomo_lab_pattern_start_r1.json'
PATTERN_ARMS = {
    'pattern_pullback': ('fomo_lab_pattern_pullback_r1.json', 'continuation', .50),
    'pattern_breakout': ('fomo_lab_pattern_breakout_r1.json', 'continuation', .50),
}
ARMS.update(PATTERN_ARMS)
FILES = {item[0] for item in ARMS.values()}

@wallet_fork(sorted(LEGACY_FILES | {MARKER}))
def bootstrap():
    present = [os.path.exists(p) for p in sorted(LEGACY_FILES | {MARKER})]
    if all(present):
        return False
    if any(present):
        raise ValueError('Inicio continuation incompleto; restaurar, no reiniciar')
    at = datetime.now(timezone.utc).isoformat()
    baseline = {'version': 'continuation-r1', 'at': at, 'initial_eur': 100,
                'scope': 'independent paper portfolios; never add balances',
                'flow_by_amount': 'UNKNOWN; count proxy only', 'execution_verified': False}
    for arm, (path, mode, ratio) in ARMS.items():
        if arm in PATTERN_ARMS:
            continue
        write(path, {'version': 1, 'started_at': at, 'cash': 100., 'reserve': 0.,
                     'positions': [], 'closed': [], 'seen': [], 'observations': [],
                     'continuation_experiment': {'version': 'continuation-r1', 'arm': arm},
                     'continuation_baseline': baseline})
    write(MARKER, baseline)
    return True

@wallet_fork(sorted({spec[0] for spec in PATTERN_ARMS.values()} | {PATTERN_MARKER}))
def bootstrap_pattern():
    paths = {spec[0] for spec in PATTERN_ARMS.values()} | {PATTERN_MARKER}
    present = [os.path.exists(path) for path in sorted(paths)]
    if all(present):
        return False
    if any(present):
        raise ValueError('Inicio pattern incompleto; restaurar, no reiniciar')
    at = datetime.now(timezone.utc).isoformat()
    baseline = {'version': 'pattern-r1', 'at': at, 'initial_eur': 100,
                'scope': 'prospective PAPER comparison; same ratio and exits; hypotheses only'}
    for arm, (path, _, _) in PATTERN_ARMS.items():
        write(path, {'version': 1, 'started_at': at, 'cash': 100., 'reserve': 0.,
                     'positions': [], 'closed': [], 'seen': [], 'observations': [],
                     'continuation_experiment': {'version': 'continuation-r1', 'arm': arm},
                     'pattern_baseline': baseline})
    write(PATTERN_MARKER, baseline)
    return True

def guard(token, allow_breakout=False):
    from candle_lab import context, evaluate_rows
    result = context(token)
    token['candle_context'] = result
    token['entry_policy_suffix'] = '+consolidation-breakout-r2' if allow_breakout else '+pullback-r2'
    token.pop('continuation_pattern', None)
    if result.get('status') == 'SIN DATOS' or not result.get('bars'):
        return 'continuation: faltan velas cerradas verificables'
    validated = evaluate_rows({'data': {'attributes': {'ohlcv_list': result['bars']}}},
                              datetime.now(timezone.utc).timestamp())
    if validated.get('status') == 'SIN DATOS':
        return 'continuation: ' + validated.get('reason', 'velas invalidas')
    token['candle_context'] = dict(result, continuation_validation=validated)
    bars = validated['bars']
    # Descriptive labels are mutually exclusive; eligibility predicates are not.
    # A valid pullback can also close above ALL previous highs, so the classifier
    # calls it BREAKOUT. Evaluate the original pullback conditions directly first.
    pause, reclaim = bars[-2:]
    research = validated['pattern_research']
    pullback = (all(row[5] > 0 for row in bars)
                and 1 <= research['pullback_pct'] <= 20
                and pause[4] < pause[1] and reclaim[4] > reclaim[1]
                and reclaim[4] > pause[2] and reclaim[3] >= pause[3]
                and research['upper_wick_fraction'] <= .4
                and reclaim[5] >= pause[5]
                and research['last_volume_multiple'] is not None
                and research['last_volume_multiple'] >= 1.2)
    if pullback:
        if bars[2][4] <= bars[0][4]:
            return 'continuation: falta impulso previo en velas cerradas'
        if not pause[2] < float(token['price']) <= reclaim[4] * 1.05:
            return 'continuation: precio fresco pierde recuperacion o se aleja >5%'
        token['continuation_pattern'] = 'PULLBACK_RECLAIM_WITH_VOLUME'
        return None
    if allow_breakout and validated['pattern_research']['name'] == 'BREAKOUT_WITH_VOLUME':
        # A pause after an impulse, not an isolated green candle or a falling range.
        a, b, c, pause, breakout = bars
        pause_range = 100 * (max(c[2], pause[2]) / min(c[3], pause[3]) - 1)
        impulse = 100 * (b[4] / a[4] - 1)
        support = min(c[3], pause[3])
        if not (2 <= impulse <= 20 and b[3] >= a[3]
                and 0 < pause_range <= 8 and support >= a[4]
                and pause[5] <= b[5] and breakout[3] >= support):
            return 'continuation: ruptura sin pausa estrecha sostenida tras impulso'
        level = max(row[2] for row in bars[:-1])
        if not level < float(token['price']) <= breakout[4] * 1.05:
            return 'continuation: precio fresco pierde ruptura o se aleja >5%'
        token['continuation_pattern'] = 'CONSOLIDATION_BREAKOUT_WITH_VOLUME'
        return None
    return 'continuation: no hay retroceso recuperado con volumen'

def breakout_guard(token):
    return guard(token, allow_breakout=True)

def candidate_universe(pairs, analyzer):
    """Same discovered pools, without the EARLY momentum veto; bounded to 20.

    This is eligibility for further checks only. Score, closed-candle guards,
    confirmation, security and wallet risk still decide every simulated entry.
    CONTROL receives the same universe and retains its EARLY momentum gates.
    """
    candidates = {}
    for pair in pairs.values():
        token = analyzer(pair, allow_nonpositive_momentum=True)
        if token is None or token['score'] < 5:
            continue
        key = (token['chain'], token['address'])
        old = candidates.get(key)
        if old is None or token['liquidity'] > old['liquidity']:
            candidates[key] = token
    return sorted(candidates.values(),
                  key=lambda t: (t['score'], t['vol5m'], t['liquidity']), reverse=True)[:20]


def run(ranking, simulator, prefetch=None):
    if bootstrap():
        print('LAB CONTINUATION INICIO: tres carteras virtuales de 100 EUR; decisiones desde proxima lectura; NO sumar')
        return
    pattern_started = bootstrap_pattern()
    if prefetch is not None:
        prefetch(ranking)  # Use the running engine's thread-local caches, including __main__.
    rows = {}
    for arm, (path, mode, ratio) in ARMS.items():
        if pattern_started and arm in PATTERN_ARMS:
            continue  # Both arms begin decisions together on the next cycle.
        simulator(ranking, path, 'LAB CONTINUATION ' + arm, confirm=True,
                  entry_mode=mode, min_buy_ratio=ratio,
                  entry_guard=(breakout_guard if arm == 'pattern_breakout' else guard) if mode == 'continuation' else None)
        with open(path) as handle:
            state = json.load(handle)
        obs = state['observations'][-1]
        rows[arm] = {'known_component': obs['verified_component'],
                     'total_equity': obs['estimated_equity'], 'open': obs['open'],
                     'closed': obs['closed'], 'entry_audit': state.get('last_entry_audit'),
                     'change_from_100': obs['verified_component'] - 100}
    print('LAB CONTINUATION COMPARACION ' + json.dumps(rows, allow_nan=False)
          + ' | 50 vs 60 difiere solo ratio; pattern_pullback vs pattern_breakout solo patron adicional, mismo inicio; flujo importe desconocido; NO rentabilidad real')


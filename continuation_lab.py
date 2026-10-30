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
FRESH_V2_FILE = 'fomo_lab_continuation_fresh_v2.json'
FRESH_V2_MARKER = 'fomo_lab_continuation_fresh_v2_start.json'
ARMS['fresh_v2'] = (FRESH_V2_FILE, 'continuation', .50)
FILES = {item[0] for item in ARMS.values()}
PATTERN_MARKER = 'fomo_lab_pattern_start_r1.json'
PATTERN_ARMS = {
    'pattern_pullback': ('fomo_lab_pattern_pullback_r1.json', 'continuation', .50),
    'pattern_breakout': ('fomo_lab_pattern_breakout_r1.json', 'continuation', .50),
}
ARMS.update(PATTERN_ARMS)
# Independent experimental arm; never restart or rewrite existing paper wallets.
SHALLOW_FILE = 'fomo_lab_shallow_pullback_r1.json'
SHALLOW_MARKER = 'fomo_lab_shallow_start_r1.json'
ARMS['shallow_pullback'] = (SHALLOW_FILE, 'continuation', .50)
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
        if arm in PATTERN_ARMS or arm in ('shallow_pullback', 'fresh_v2'):
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

@wallet_fork([SHALLOW_FILE, SHALLOW_MARKER])
def bootstrap_shallow():
    paths = [SHALLOW_FILE, SHALLOW_MARKER]
    present = [os.path.exists(path) for path in paths]
    if all(present):
        return False
    if any(present):
        raise ValueError('Inicio shallow incompleto; restaurar, no reiniciar')
    at = datetime.now(timezone.utc).isoformat()
    baseline = {'version': 'shallow-r1', 'at': at, 'initial_eur': 100,
                'scope': 'independent paper wallet; 8-22% pullback vs original 12-22%',
                'profitability_verified': False}
    write(SHALLOW_FILE, {'version': 1, 'started_at': at, 'cash': 100.,
                         'reserve': 0., 'positions': [], 'closed': [],
                         'seen': [], 'observations': [],
                         'continuation_experiment': {'version': 'shallow-r1',
                                                     'arm': 'shallow_pullback'},
                         'shallow_baseline': baseline})
    write(SHALLOW_MARKER, baseline)
    return True



@wallet_fork([FRESH_V2_FILE, FRESH_V2_MARKER])
def bootstrap_fresh_v2():
    """Start an independent 100 EUR PAPER epoch; never overwrite an existing wallet."""
    present = [os.path.exists(p) for p in (FRESH_V2_FILE, FRESH_V2_MARKER)]
    if all(present):
        return False
    if any(present):
        raise ValueError('Fresh V2 partial restore: refusing to reset or fabricate cash')
    at = datetime.now(timezone.utc).isoformat()
    baseline = {'version': 'continuation-fresh-v2', 'at': at,
                'initial_eur': 100.0, 'paper_only': True,
                'scope': 'independent wallet; historical CONTROL/Coin/GTA untouched'}
    write(FRESH_V2_FILE, {'version': 1, 'started_at': at,
                          'cash': 100.0, 'reserve': 0.0,
                          'positions': [], 'closed': [], 'seen': [],
                          'observations': [],
                          'continuation_experiment': {'version': 'continuation-r1',
                                                      'arm': 'fresh_v2'},
                          'fresh_v2_baseline': baseline})
    write(FRESH_V2_MARKER, baseline)
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

def gradual_guard(token, *, min_pullback=12):
    """Gradual impulse, bounded pullback and two-bar reclaim; PAPER only."""
    if min_pullback not in (8, 12):
        raise ValueError('Unsupported experimental pullback depth')
    from candle_lab import context, evaluate_rows
    result = context(token)
    token['entry_policy_suffix'] = ('+shallow-pullback-r1' if min_pullback == 8
                                    else '+gradual-pullback-r1')
    token.pop('continuation_pattern', None)
    checked = evaluate_rows({'data': {'attributes': {'ohlcv_list':
        result.get('closed_history', result.get('bars', []))}}},
        datetime.now(timezone.utc).timestamp())
    token['candle_context'] = dict(result, gradual_validation=checked)
    if checked.get('status') == 'SIN DATOS':
        return 'gradual: ' + checked.get('reason', 'velas invalidas')
    bars = checked['closed_history']
    if len(bars) < 10 or any(b[0]-a[0] != 60 for a,b in zip(bars,bars[1:])):
        return 'gradual: faltan diez velas consecutivas cerradas'
    if any(r[5] <= 0 for r in bars):
        return 'gradual: intervalos sin volumen'
    peak_i = max(range(len(bars)-3), key=lambda i: bars[i][2])
    if peak_i < 3:
        return 'gradual: impulso previo demasiado corto'
    peak = bars[peak_i][2]
    impulse = (peak/bars[0][1]-1)*100
    if not 10 <= impulse <= 60 or any(abs(r[4]/r[1]-1)*100 > 15 for r in bars[:peak_i+1]):
        return 'gradual: impulso ausente o demasiado vertical'
    pullback = bars[peak_i+1:-2]
    if not 2 <= len(pullback) <= 8:
        return 'gradual: retroceso fuera de 2-8 minutos'
    # A multi-minute total drawdown can hide a single abrupt collapse.
    # Reject a >=12% low relative to the preceding close within one minute,
    # including an opening gap or a recovered wick. Never infer a future rug.
    prior_close = bars[peak_i][4]
    for bar in bars[peak_i+1:]:
        if bar[3] <= prior_close * .88:
            return 'gradual: desplome intraminuto >=12%'
        prior_close = bar[4]
    trough = min(r[3] for r in pullback)
    depth = (1-trough/peak)*100
    a,b = bars[-2:]
    baseline = sum(r[5] for r in pullback)/len(pullback)
    wick = (b[2]-max(b[1],b[4]))/(b[2]-b[3]) if b[2]>b[3] else 0
    if not min_pullback <= depth <= 22:
        return f'gradual: retroceso fuera de {min_pullback}-22%'
    if not (a[4]>a[1] and b[4]>b[1] and b[4]>a[2]
            and a[3]>=trough and b[3]>=a[3] and b[4]>=trough*1.03):
        return 'gradual: recuperacion no confirmada o pierde soporte'
    if b[5] < baseline*1.2 or b[5] < a[5] or wick > .4:
        return 'gradual: recuperacion sin volumen o con rechazo superior'
    if not a[2] < float(token['price']) <= b[4]*1.05:
        return 'gradual: precio pierde recuperacion o se aleja >5%'
    token['continuation_pattern'] = 'GRADUAL_IMPULSE_ORDERED_PULLBACK_RECLAIM'
    token['gradual_pattern_evidence'] = {'version': ('shallow-pullback-r1' if min_pullback == 8 else 'gradual-pullback-r1'),
        'impulse_pct':impulse, 'pullback_pct':depth, 'pullback_minutes':len(pullback),
        'volume_multiple':b[5]/baseline, 'peak_price':peak, 'support_price':trough,
        'future_target_verified':False}
    return None

def shallow_guard(token):
    """Experimental 8-22% pullback with all original safety and volume checks."""
    return gradual_guard(token, min_pullback=8)


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
    shallow_started = bootstrap_shallow()
    fresh_started = bootstrap_fresh_v2()
    if fresh_started:
        print('LAB CONTINUATION FRESH V2: isolated PAPER 100 EUR bootstrapped; entries next cycle')
    if prefetch is not None:
        prefetch(ranking)  # Use the running engine's thread-local caches, including __main__.
    rows = {}
    for arm, (path, mode, ratio) in ARMS.items():
        if pattern_started and arm in PATTERN_ARMS:
            continue  # Both pattern arms begin decisions together next cycle.
        if shallow_started and arm == 'shallow_pullback':
            continue  # New isolated wallet starts decisions next cycle.
        if fresh_started and arm == 'fresh_v2':
            continue  # Do not trade on the wallet creation cycle.
        simulator(ranking, path, 'LAB CONTINUATION ' + arm, confirm=True,
                  entry_mode=mode, min_buy_ratio=ratio,
                  entry_guard=(breakout_guard if arm == 'pattern_breakout' else
                               gradual_guard if arm == 'pattern_pullback' else
                               shallow_guard if arm == 'shallow_pullback' else guard) if mode == 'continuation' else None)
        with open(path) as handle:
            state = json.load(handle)
        obs = state['observations'][-1]
        rows[arm] = {'known_component': obs['verified_component'],
                     'total_equity': obs['estimated_equity'], 'open': obs['open'],
                     'closed': obs['closed'], 'entry_audit': state.get('last_entry_audit'),
                     'change_from_100': obs['verified_component'] - 100}
    print('LAB CONTINUATION COMPARACION ' + json.dumps(rows, allow_nan=False)
          + ' | shallow_pullback uses 8-22pct vs pattern_pullback 12-22pct; separate start date; no direct equity comparison across different start dates; NO rentabilidad real')


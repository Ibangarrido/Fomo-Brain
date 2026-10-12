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
FILES = {item[0] for item in ARMS.values()}

@wallet_fork(sorted(FILES | {MARKER}))
def bootstrap():
    present = [os.path.exists(p) for p in sorted(FILES | {MARKER})]
    if all(present):
        return False
    if any(present):
        raise ValueError('Inicio continuation incompleto; restaurar, no reiniciar')
    at = datetime.now(timezone.utc).isoformat()
    baseline = {'version': 'continuation-r1', 'at': at, 'initial_eur': 100,
                'scope': 'independent paper portfolios; never add balances',
                'flow_by_amount': 'UNKNOWN; count proxy only', 'execution_verified': False}
    for arm, (path, mode, ratio) in ARMS.items():
        write(path, {'version': 1, 'started_at': at, 'cash': 100., 'reserve': 0.,
                     'positions': [], 'closed': [], 'seen': [], 'observations': [],
                     'continuation_experiment': {'version': 'continuation-r1', 'arm': arm},
                     'continuation_baseline': baseline})
    write(MARKER, baseline)
    return True

def guard(token):
    from candle_lab import context, evaluate_rows
    result = context(token)
    token['candle_context'] = result
    token['entry_policy_suffix'] = '+pullback-r1'
    if result.get('status') == 'SIN DATOS' or not result.get('bars'):
        return 'continuation: faltan velas cerradas verificables'
    validated = evaluate_rows({'data': {'attributes': {'ohlcv_list': result['bars']}}},
                              datetime.now(timezone.utc).timestamp())
    if validated.get('status') == 'SIN DATOS':
        return 'continuation: ' + validated.get('reason', 'velas invalidas')
    token['candle_context'] = dict(result, continuation_validation=validated)
    bars = validated['bars']
    if validated['pattern_research']['name'] != 'PULLBACK_RECLAIM_WITH_VOLUME':
        return 'continuation: no hay retroceso recuperado con volumen'
    if bars[2][4] <= bars[0][4]:
        return 'continuation: falta impulso previo en velas cerradas'
    if not bars[-2][2] < float(token['price']) <= bars[-1][4] * 1.05:
        return 'continuation: precio fresco pierde recuperacion o se aleja >5%'
    return None

def run(ranking, simulator):
    if bootstrap():
        print('LAB CONTINUATION INICIO: tres carteras virtuales de 100 EUR; decisiones desde proxima lectura; NO sumar')
        return
    rows = {}
    for arm, (path, mode, ratio) in ARMS.items():
        simulator(ranking, path, 'LAB CONTINUATION ' + arm, confirm=True,
                  entry_mode=mode, min_buy_ratio=ratio,
                  entry_guard=guard if mode == 'continuation' else None)
        with open(path) as handle:
            state = json.load(handle)
        obs = state['observations'][-1]
        rows[arm] = {'known_component': obs['verified_component'],
                     'total_equity': obs['estimated_equity'], 'open': obs['open'],
                     'closed': obs['closed'], 'entry_audit': state.get('last_entry_audit'),
                     'change_from_100': obs['verified_component'] - 100}
    print('LAB CONTINUATION COMPARACION ' + json.dumps(rows, allow_nan=False)
          + ' | 50 vs 60 difiere solo ratio; control cambia estrategia; flujo importe desconocido; NO rentabilidad real')

"""Fresh, isolated prospective virtual exit-policy experiment."""
import copy
import json
import os
from datetime import datetime, timezone
from exit_watchdog import wallet_fork
from m4_lab import write

CONTROL = 'fomo_lab_targets_control_r1.json'
STAGED = 'fomo_lab_targets_staged_r1.json'
MARKER = 'fomo_lab_targets_start_r1.json'
FILES = (CONTROL, STAGED)


@wallet_fork([CONTROL, STAGED, MARKER])
def bootstrap():
    present = [os.path.exists(p) for p in (*FILES, MARKER)]
    if all(present):
        return False
    if any(present):
        raise ValueError('Laboratorio targets incompleto; restaurar, nunca reiniciar')
    at = datetime.now(timezone.utc).isoformat()
    for arm, path in zip(('control', 'staged'), FILES):
        write(path, {'version': 1, 'started_at': at, 'cash': 100., 'reserve': 0.,
                     'positions': [], 'closed': [], 'seen': [], 'observations': [],
                     'targets_experiment': {'version': 'targets-r1', 'arm': arm},
                     'targets_baseline': {'at': at, 'equity': 100.}})
    write(MARKER, {'version': 'targets-r1', 'at': at, 'files': list(FILES)})
    print('LAB TARGETS INICIO: dos carteras nuevas de 100 EUR virtuales; NO sumar')
    return True


def decision(pos, pnl, age):
    """Thresholds use net return on remaining allocated cost; fills at observed price."""
    stage = pos.get('targets_stage', 0)
    if pnl <= -15:
        return 'STOP -15%', False, 1., stage
    if stage and pnl <= 2:
        return 'TARGETS PROTECCION +2%', False, 1., stage
    if age >= 24:
        return 'TIEMPO 24h', False, 1., stage
    # A gap across several targets produces one fill at the observed quote.
    if pnl >= 45:
        return 'TARGETS TP3 +45%', False, 1., 3
    if pnl >= 30 and stage < 2:
        return 'TARGETS TP2 +30%', True, .75 if stage == 0 else .5, 2
    if pnl >= 15 and stage == 0:
        return 'TARGETS TP1 +15%', True, .5, 1
    return None, False, 1., stage


def report():
    rows = {}
    for arm, path in zip(('control', 'staged'), FILES):
        with open(path) as handle:
            state = json.load(handle)
        obs = state['observations'][-1] if state['observations'] else None
        complete = obs is None or obs['valuation_complete']
        equity = obs['estimated_equity'] if obs else 100.
        # Count completed positions, not partial sales, as trials.
        opened = {p['opened_at'] + ':' + p['chain'] + ':' + p['address'] for p in state['positions']}
        groups = {}
        for sale in state['closed']:
            key = sale['opened_at'] + ':' + sale['chain'] + ':' + sale['address']
            groups[key] = groups.get(key, 0.) + sale['profit']
        completed = [v for k, v in groups.items() if k not in opened]
        rows[arm] = {'equity': equity if complete else None,
                     'delta': equity - 100 if complete else None,
                     'realized': sum(p['profit'] for p in state['closed']),
                     'completed_positions': len(completed),
                     'winning_positions': sum(v > 0 for v in completed),
                     'open': len(state['positions']),
                     'unknown': obs['unverified_quotes'] if obs else 0}
    a, b = rows['control']['delta'], rows['staged']['delta']
    rows['advantage'] = b - a if a is not None and b is not None else None
    print('LAB TARGETS COMPARACION ' + json.dumps(rows, allow_nan=False))
    return rows


def run(ranking, simulator):
    if bootstrap():
        return
    from candle_lab import guard
    for arm, path in zip(('control', 'staged'), FILES):
        simulator(copy.deepcopy(ranking), path, 'LAB TARGETS ' + arm.upper(),
                  entry_guard=guard(True, 'early', 'LAB TARGETS'),
                  staged_targets=arm == 'staged')
    report()

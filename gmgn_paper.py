"""Independent GMGN paper-study ledger, initialized once; no financial operations."""
import json
import math
import os
from datetime import datetime, timezone

FILE = 'gmgn_paper_r1.json'
SEED = 'gmgn_paper_start_r1.json'
PREFLIGHT = 'gmgn_preflight.json'


def read_json(path):
    with open(path) as handle:
        return json.load(handle)


def update(path=FILE, seed_path=SEED, preflight_path=PREFLIGHT):
    state = read_json(path if os.path.exists(path) else seed_path)
    if state.get('version') != 'gmgn-paper-r1' or state.get('initial_capital_eur') != 100:
        raise ValueError('GMGN ledger incompatible; do not reset')
    for field in ('cash_eur', 'reserve_eur'):
        value = state.get(field)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid GMGN balance; do not reset')
    if not isinstance(state.get('positions'), list) or not isinstance(state.get('closed'), list):
        raise ValueError('Invalid GMGN history; do not reset')
    try:
        preflight = read_json(preflight_path)
        source_status = preflight.get('status', 'UNAVAILABLE')
    except FileNotFoundError:
        source_status = 'NO_PREFLIGHT'
    # Preflight schemas and browser snapshots are not normalized trading data.
    # Do not synthesize fills or count historical snapshots as fresh signals.
    state['status'] = 'AWAITING_VALIDATED_GMGN_DATA'
    state['source_status'] = source_status
    state['execution_enabled'] = False
    state['paper_entries_enabled'] = False
    state['observations'].append({
        'at': datetime.now(timezone.utc).isoformat(), 'source_status': source_status,
        'cash_eur': state['cash_eur'], 'reserve_eur': state['reserve_eur'],
        'open': len(state['positions']), 'closed': len(state['closed']),
        'market_observation': False, 'new_entries': 0,
        'blocker': 'Validate authenticated GMGN market response schema, units, identity and timestamps before paper entries'})
    state['observations'] = state['observations'][-3000:]
    with open(path + '.tmp', 'w') as handle:
        json.dump(state, handle, indent=2, allow_nan=False)
    os.replace(path + '.tmp', path)
    print('GMGN PAPER ' + json.dumps({k: state[k] for k in (
        'status', 'source_status', 'cash_eur', 'reserve_eur', 'paper_entries_enabled')}))
    return state


if __name__ == '__main__':
    update()

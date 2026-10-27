"""Cooker public Solana observer. No orders, signing, fills or claimed paper PnL."""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

WALLET = '8deJ9xeUvXSJwicYptA9mHsU2rN2pDx37KWzkDkEXhU6'
RPC = 'https://api.mainnet-beta.solana.com'
FILE = 'cooker_tracking_r1.json'
WSOL = 'So11111111111111111111111111111111111111112'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def rpc(method, params):
    if method not in ('getSignaturesForAddress', 'getTransaction'):
        raise ValueError('Read-only methods only')
    request = urllib.request.Request(RPC, data=json.dumps({
        'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params
    }).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError('Oversized RPC response')
    envelope = json.loads(raw)
    if 'error' in envelope or 'result' not in envelope:
        raise ValueError('RPC unavailable')
    return envelope['result']


def classify(tx, signature):
    if not isinstance(tx, dict) or not isinstance(tx.get('meta'), dict):
        raise ValueError('Transaction not available yet')
    meta = tx['meta']
    event = {'signature': signature, 'slot': tx['slot'], 'block_time': tx.get('blockTime'),
             'observed_at': stamp(), 'kind': 'OTHER', 'paper_fill': False}
    if meta.get('err') is not None:
        return dict(event, kind='FAILED')
    message = tx['transaction']['message']
    keys = message['accountKeys']
    signed = any(isinstance(k, dict) and k.get('pubkey') == WALLET and k.get('signer') for k in keys)
    totals = []
    for side in ('preTokenBalances', 'postTokenBalances'):
        balances = {}
        for row in meta.get(side) or []:
            if row.get('owner') != WALLET:
                continue
            amount = row['uiTokenAmount']
            value = Decimal(amount['amount']) / (Decimal(10) ** amount['decimals'])
            balances[row['mint']] = balances.get(row['mint'], Decimal(0)) + value
        totals.append(balances)
    before, after = totals
    deltas = {mint: after.get(mint, Decimal(0)) - before.get(mint, Decimal(0))
              for mint in before.keys() | after.keys()}
    event['token_deltas'] = {m: str(v) for m, v in deltas.items() if v}
    event['wallet_signed'] = signed
    # Balance deltas alone do not prove a swap, its paid price or profitability.
    event['kind'] = 'SIGNED_TOKEN_CHANGE' if signed and event['token_deltas'] else 'UNSIGNED_OR_OTHER'
    event['requires_swap_verification'] = bool(signed and event['token_deltas'])
    return event


def collect(state, fetch=rpc, pause=time.sleep):
    if state.get('wallet', WALLET) != WALLET:
        raise ValueError('Wrong wallet state')
    state.update(version='cooker-watch-r1', wallet=WALLET, execution_enabled=False,
                 paper_entries_enabled=False, checked_at=stamp())
    state.setdefault('events', [])
    cursor = state.get('cursor')
    # Resume a bounded history scan across runs instead of restarting at the
    # newest 100 signatures forever. Never rebaseline an existing cursor.
    pending = state.setdefault('catchup', {
        'cursor': cursor, 'rows': [], 'before': None, 'found': False})
    if pending.get('cursor') != cursor:
        raise ValueError('Catchup cursor mismatch; refusing to skip history')
    rows = pending['rows']
    if not pending['found']:
        for _ in range(5):
            opts = {'limit': 20, 'commitment': 'finalized'}
            if pending['before']:
                opts['before'] = pending['before']
            page = fetch('getSignaturesForAddress', [WALLET, opts])
            if not isinstance(page, list):
                raise ValueError('Invalid signatures response')
            if not cursor:
                if page:
                    state['cursor'] = page[0]['signature']
                    state['started_at'] = stamp()
                state.pop('catchup', None)
                state['status'] = 'BASELINE_SET' if page else 'WAITING_FOR_BASELINE'
                state['new_events'] = 0
                return state
            seen_rows = {r['signature'] for r in rows}
            for row in page:
                if row['signature'] == cursor:
                    pending['found'] = True
                    break
                if row['signature'] not in seen_rows:
                    rows.append(row)
                    seen_rows.add(row['signature'])
            if pending['found']:
                break
            if len(page) < 20:
                state.update(status='HISTORY_GAP_CURSOR_RETAINED', new_events=0)
                return state
            next_before = page[-1]['signature']
            if next_before == pending['before']:
                raise ValueError('History pagination did not advance')
            pending['before'] = next_before
            pause(1)
        if not pending['found']:
            state.update(status='HISTORY_CATCHUP_SCANNING', new_events=0,
                         pending_signatures=len(rows))
            return state
        pending['newest'] = rows[0]['signature'] if rows else cursor
    seen = {e['signature'] for e in state['events']}
    count = 0
    # Decode oldest first, at most 20 per run. On error, keep the failed row
    # and completed events so a retry neither skips nor duplicates a receipt.
    while rows and count < 20:
        row = rows[-1]
        if row['signature'] in seen:
            rows.pop()
            continue
        pause(1)
        tx = fetch('getTransaction', [row['signature'], {
            'encoding': 'jsonParsed', 'commitment': 'finalized', 'maxSupportedTransactionVersion': 0}])
        event = classify(tx, row['signature'])
        state['events'].append(event)
        seen.add(row['signature'])
        rows.pop()
        count += 1
    state['events'] = state['events'][-5000:]
    state.update(new_events=count, pending_signatures=len(rows))
    if rows:
        state['status'] = 'HISTORY_CATCHUP_DECODING'
    else:
        state['cursor'] = pending['newest']
        state.pop('catchup', None)
        state.update(status='SYNCED', last_success_at=stamp())
        state.pop('error_type', None)
    return state


def main():
    try:
        with open(FILE) as handle:
            state = json.load(handle)
    except FileNotFoundError:
        state = {'wallet': WALLET, 'events': []}
    if state.get('wallet') != WALLET:
        raise ValueError('Wrong wallet state; refusing overwrite')
    try:
        collect(state)
    except Exception as exc:
        state.update(status='UNAVAILABLE_RETRY_NEXT_RUN', error_type=type(exc).__name__,
                     checked_at=stamp(), new_events=None)
    with open(FILE + '.tmp', 'w') as handle:
        json.dump(state, handle, indent=2, allow_nan=False)
    os.replace(FILE + '.tmp', FILE)
    summary = {k: state.get(k) for k in ('wallet', 'status', 'checked_at', 'new_events', 'error_type')}
    print('COOKER WATCH ' + json.dumps(summary), flush=True)
    print('Observation only; no paper fills or real orders. Schedule may have gaps.', flush=True)


if __name__ == '__main__':
    main()

"""Read-only discovery of new Solana pools; never places orders."""
import json
import math
import os
import urllib.request
from datetime import datetime, timezone

URL = 'https://api.geckoterminal.com/api/v2/networks/solana/new_pools'


def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) and x >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def evaluate(payload):
    rows = []
    data = payload.get('data', []) if isinstance(payload, dict) else []
    for p in data if isinstance(data, list) else []:
        if not isinstance(p, dict):
            continue
        a = p.get('attributes') or {}
        if not isinstance(a, dict):
            continue
        pool = a.get('address')
        created = a.get('pool_created_at')
        price_usd = num(a.get('base_token_price_usd'))
        liquidity = num(a.get('reserve_in_usd'))
        volumes = a.get('volume_usd') or {}
        vol = num(volumes.get('m5')) if isinstance(volumes, dict) else None
        transactions = a.get('transactions') or {}
        tx = (transactions.get('m5') or {}) if isinstance(transactions, dict) else {}
        buys, sells = (num(tx.get('buys')), num(tx.get('sells'))) if isinstance(tx, dict) else (None, None)
        if not isinstance(pool, str) or not pool:
            continue
        reasons = []
        if not isinstance(created, str) or not created: reasons.append('missing_creation_time')
        if liquidity is None or liquidity < 20000: reasons.append('liquidity')
        if vol is None or vol < 5000: reasons.append('volume_5m')
        if buys is None or sells is None or buys + sells < 40: reasons.append('trades_5m')
        elif buys / (buys + sells) < .5: reasons.append('buy_count_ratio')
        rows.append({'pool': pool, 'pool_created_at': created, 'price_usd': price_usd, 'liquidity_usd': liquidity, 'volume_5m_usd': vol,
                     'buys_5m': buys, 'sells_5m': sells, 'watch': not reasons,
                     'reasons': reasons, 'buy_volume_usd_verified': False,
                     'price_freshness_verified': False, 'paper_entry': False, 'exit_verified': False})
    return rows



def history_update(previous, rows, observed_at):
    """Append actual observations only; never backfill candles or claim fills."""
    history = previous.get('history', {}) if isinstance(previous, dict) else {}
    if not isinstance(history, dict):
        history = {}
    for row in rows:
        # Continue tracking previously discovered pools even if they fail today's filters.
        if not row['watch'] and row['pool'] not in history:
            continue
        pool = row['pool']
        record = history.get(pool, {'first_seen': observed_at, 'samples': []})
        if not isinstance(record, dict) or not isinstance(record.get('samples'), list):
            record = {'first_seen': observed_at, 'samples': []}
        sample = {'at': observed_at, 'price_usd': row['price_usd'],
                  'liquidity_usd': row['liquidity_usd'], 'volume_5m_usd': row['volume_5m_usd']}
        if not record['samples'] or record['samples'][-1].get('at') != observed_at:
            record['samples'].append(sample)
        record['samples'] = record['samples'][-96:]
        history[pool] = record
    # Bound memory and preserve the most recently observed candidates.
    history = dict(sorted(history.items(), key=lambda item: item[1].get('samples', [{}])[-1].get('at', ''), reverse=True)[:300])
    return history


def run():
    status = 'OK'
    try:
        req = urllib.request.Request(URL, headers={'Accept': 'application/json;version=20230203', 'User-Agent': 'FomoBrainResearch/1.0'})
        with urllib.request.urlopen(req, timeout=12) as response:
            rows = evaluate(json.load(response))
    except Exception as exc:
        rows, status = [], 'UNAVAILABLE:' + type(exc).__name__
    try:
        with open('discovery_watch.json') as f:
            previous = json.load(f)
    except (OSError, ValueError):
        previous = {}
    report = {'version': 'discovery-watch-r2', 'at': datetime.now(timezone.utc).isoformat(),
              'source': URL, 'status': status, 'snapshot_only': True,
              'not_trade_signals': True, 'watch_count': sum(x['watch'] for x in rows), 'candidates': rows,
              'history': history_update(previous, rows, datetime.now(timezone.utc).isoformat())}
    with open('discovery_watch.json.tmp', 'w') as f: json.dump(report, f, allow_nan=False, indent=2)
    os.replace('discovery_watch.json.tmp', 'discovery_watch.json')
    print('DISCOVERY WATCH', status, len(rows), 'pools', report['watch_count'], 'watch candidates')
    return report


if __name__ == '__main__': run()

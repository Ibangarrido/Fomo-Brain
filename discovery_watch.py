"""Read-only discovery of new Solana pools; never places orders."""
import json
import math
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
    for p in payload.get('data', []):
        a = p.get('attributes') or {}
        pool = a.get('address')
        liquidity = num(a.get('reserve_in_usd'))
        vol = num((a.get('volume_usd') or {}).get('m5'))
        tx = (a.get('transactions') or {}).get('m5') or {}
        buys, sells = num(tx.get('buys')), num(tx.get('sells'))
        if not isinstance(pool, str) or not pool:
            continue
        reasons = []
        if liquidity is None or liquidity < 20000: reasons.append('liquidity')
        if vol is None or vol < 5000: reasons.append('volume_5m')
        if buys is None or sells is None or buys + sells < 40: reasons.append('trades_5m')
        elif buys / (buys + sells) < .5: reasons.append('buy_count_ratio')
        rows.append({'pool': pool, 'liquidity_usd': liquidity, 'volume_5m_usd': vol,
                     'buys_5m': buys, 'sells_5m': sells, 'watch': not reasons,
                     'reasons': reasons, 'paper_entry': False, 'exit_verified': False})
    return rows


def run():
    status = 'OK'
    try:
        req = urllib.request.Request(URL, headers={'Accept': 'application/json;version=20230203', 'User-Agent': 'FomoBrainResearch/1.0'})
        with urllib.request.urlopen(req, timeout=12) as response:
            rows = evaluate(json.load(response))
    except Exception as exc:
        rows, status = [], 'UNAVAILABLE:' + type(exc).__name__
    report = {'version': 'discovery-watch-r1', 'at': datetime.now(timezone.utc).isoformat(),
              'source': URL, 'status': status, 'snapshot_only': True,
              'not_trade_signals': True, 'watch_count': sum(x['watch'] for x in rows), 'candidates': rows}
    with open('discovery_watch.json.tmp', 'w') as f: json.dump(report, f, allow_nan=False, indent=2)
    import os
    os.replace('discovery_watch.json.tmp', 'discovery_watch.json')
    print('DISCOVERY WATCH', status, len(rows), 'pools', report['watch_count'], 'watch candidates')
    return report


if __name__ == '__main__': run()

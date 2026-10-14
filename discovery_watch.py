"""Read-only discovery of new Solana pools; never places orders."""
import json
import math
from collections import defaultdict
from collections import Counter
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone

URL = 'https://api.geckoterminal.com/api/v2/networks/solana/new_pools'
WATCH_MIN_LIQUIDITY_USD = 8000
WATCH_MIN_VOLUME_5M_USD = 1500
WATCH_MIN_TRADES_5M = 15
WATCH_MAX_GAIN_1H_PCT = 100
MAX_TRACKED = 20
MAX_HISTORY = 300
MAX_SAMPLES = 96
MIN_OBSERVATION_GAP_SECONDS = 600


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
        changes = a.get('price_change_percentage') or {}
        gain_1h = None
        if isinstance(changes, dict):
            try:
                value = float(changes.get('h1'))
                if math.isfinite(value): gain_1h = value
            except (ValueError, TypeError, OverflowError):
                pass
        reasons = []
        if price_usd is None or price_usd <= 0: reasons.append('missing_valid_price')
        if gain_1h is None: reasons.append('missing_gain_1h')
        elif gain_1h > WATCH_MAX_GAIN_1H_PCT: reasons.append('gain_1h_over_limit')
        if not isinstance(created, str) or not created: reasons.append('missing_creation_time')
        if liquidity is None or liquidity < WATCH_MIN_LIQUIDITY_USD: reasons.append('liquidity')
        if vol is None or vol < WATCH_MIN_VOLUME_5M_USD: reasons.append('volume_5m')
        if buys is None or sells is None or buys + sells < WATCH_MIN_TRADES_5M: reasons.append('trades_5m')
        elif buys / (buys + sells) < .5: reasons.append('buy_count_ratio')
        rows.append({'pool': pool, 'pool_created_at': created, 'price_usd': price_usd, 'gain_1h_pct': gain_1h, 'liquidity_usd': liquidity, 'volume_5m_usd': vol,
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
        eligible_near_miss = len(row['reasons']) == 1 and row['reasons'][0] not in ('missing_valid_price', 'missing_creation_time', 'missing_gain_1h')
        if not row['watch'] and not eligible_near_miss and row['pool'] not in history:
            continue
        pool = row['pool']
        record = history.get(pool, {'first_seen': observed_at, 'samples': []})
        if not isinstance(record, dict) or not isinstance(record.get('samples'), list):
            record = {'first_seen': observed_at, 'samples': []}
        if row['price_usd'] is None or row['price_usd'] <= 0:
            continue
        sample = {'at': observed_at, 'price_usd': row['price_usd'],
                  'liquidity_usd': row['liquidity_usd'], 'volume_5m_usd': row['volume_5m_usd']}
        if not record['samples'] or record['samples'][-1].get('at') != observed_at:
            record['samples'].append(sample)
        record['samples'] = record['samples'][-MAX_SAMPLES:]
        history[pool] = record
    # Bound memory and preserve the most recently observed candidates.
    history = dict(sorted(history.items(), key=lambda item: item[1].get('samples', [{}])[-1].get('at', ''), reverse=True)[:MAX_HISTORY])
    return history



def fetch_tracked(previous, existing_pools, limit=MAX_TRACKED):
    """Requote up to 20 previously seen Solana pools in one bounded API call."""
    history = previous.get('history', {}) if isinstance(previous, dict) else {}
    if not isinstance(history, dict):
        return [], 0
    ordered = sorted(
        ((pool, record) for pool, record in history.items()
         if isinstance(pool, str) and pool not in existing_pools and
         isinstance(record, dict) and isinstance(record.get('samples'), list) and record['samples']),
        key=lambda item: item[1]['samples'][-1].get('at', '') if isinstance(item[1]['samples'][-1], dict) else '',
        reverse=True,
    )
    missing = [pool for pool, _ in ordered[:limit]]
    if not missing:
        return [], 0
    try:
        addresses = ','.join(urllib.parse.quote(pool, safe='') for pool in missing)
        url = 'https://api.geckoterminal.com/api/v2/networks/solana/pools/multi/' + addresses
        req = urllib.request.Request(url, headers={'Accept': 'application/json;version=20230203',
                                                   'User-Agent': 'FomoBrainResearch/1.0'})
        with urllib.request.urlopen(req, timeout=12) as response:
            payload = json.load(response)
        rows = evaluate(payload)
        expected = set(missing)
        found = {}
        for row in rows:
            if row['pool'] in expected:
                found[row['pool']] = row
        return list(found.values()), len(expected - set(found))
    except Exception:
        return [], len(missing)


def performance(history, minutes, tolerance_minutes=8):
    """Observed price change only; not executable PnL or a backfilled candle."""
    result = {}
    for pool, record in history.items():
        if not isinstance(record, dict):
            continue
        samples = record.get('samples')
        if not isinstance(samples, list) or not samples:
            continue
        valid = []
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            price = num(sample.get('price_usd'))
            if price is None or price <= 0:
                continue
            try:
                when = datetime.fromisoformat(sample['at'].replace('Z', '+00:00'))
                if when.tzinfo is None:
                    continue
                valid.append((when, price))
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
        valid.sort()
        if not valid:
            continue
        first_time, first_price = valid[0]
        measurements = {}
        for horizon in minutes:
            target = horizon * 60
            eligible = [(abs((when - first_time).total_seconds() - target), price)
                        for when, price in valid[1:]
                        if abs((when - first_time).total_seconds() - target) <= tolerance_minutes * 60]
            measurements[str(horizon) + 'm_pct'] = (
                round((min(eligible)[1] / first_price - 1) * 100, 3) if eligible else None
            )
        result[pool] = {'first_observed_at': first_time.isoformat(),
                        'valid_observations': len(valid), 'observed_change_pct': measurements,
                        'not_trade_pnl': True}
    return result


def diagnostics(rows):
    """Explain rejected pools without weakening entry gates or claiming trades."""
    rejected = [row for row in rows if not row['watch']]
    counts = Counter(reason for row in rejected for reason in row['reasons'])
    near = [row for row in rejected if len(row['reasons']) == 1 and
            row['reasons'][0] not in ('missing_valid_price', 'missing_creation_time')]
    return {'rejected': len(rejected), 'reason_counts': dict(sorted(counts.items())),
            'near_miss_count': len(near),
            'near_misses': [{'pool': row['pool'], 'reason': row['reasons'][0],
                             'liquidity_usd': row['liquidity_usd'],
                             'volume_5m_usd': row['volume_5m_usd'],
                             'buys_5m': row['buys_5m'], 'sells_5m': row['sells_5m']}
                            for row in near[:20]],
            'near_misses_are_not_trade_signals': True}


def pattern_study(history):
    """Prospective price-path labels, never entry signals or evidence of profit."""
    output = {}
    for pool, record in history.items():
        samples = record.get('samples', []) if isinstance(record, dict) else []
        valid = []
        for sample in samples if isinstance(samples, list) else []:
            if not isinstance(sample, dict):
                continue
            price = num(sample.get('price_usd'))
            liquidity = num(sample.get('liquidity_usd'))
            if price is None or price <= 0 or liquidity is None or liquidity < WATCH_MIN_LIQUIDITY_USD:
                continue
            try:
                at = datetime.fromisoformat(sample['at'].replace('Z', '+00:00'))
                if at.tzinfo is None:
                    continue
                valid.append((at, price))
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
        valid.sort(key=lambda item: item[0])
        if len(valid) < 3:
            continue
        # Distinct observations at least 10 minutes apart; avoid treating repeats as candles.
        distinct = []
        for item in valid:
            if not distinct or (item[0] - distinct[-1][0]).total_seconds()  >= MIN_OBSERVATION_GAP_SECONDS:
                distinct.append(item)
        if len(distinct) < 3:
            continue
        recent = distinct[-3:]
        if (recent[-1][0] - recent[0][0]).total_seconds() > 7200:
            continue
        a, b, d = [item[1] for item in recent]
        move1, move2 = (b / a - 1) * 100, (d / b - 1) * 100
        if move1 >= 3 and move2 >= 3:
            label = 'two_rising_observations'
        elif move1 <= -3 and move2 <= -3:
            label = 'two_falling_observations'
        elif move1 >= 5 and move2 <= -3:
            label = 'rise_then_pullback'
        elif move1 <= -5 and move2 >= 3:
            label = 'fall_then_rebound'
        else:
            label = 'mixed_or_flat'
        output[pool] = {'pattern': label, 'moves_pct': [round(move1, 3), round(move2, 3)],
                        'sample_times': [item[0].isoformat() for item in recent],
                        'price_path_only': True, 'trade_signal': False,
                        'gmgn_data': False}
    return output


def pattern_outcomes(history, patterns, minutes=(15, 30), tolerance_minutes=8):
    """Forward-only evaluation: classify at the middle sample, score later quotes."""
    outcomes = defaultdict(lambda: {'evaluated': 0, 'positive': 0, 'returns_pct': []})
    for pool, item in patterns.items():
        samples = history.get(pool, {}).get('samples', [])
        try:
            observed = []
            for sample in samples:
                price = num(sample.get('price_usd'))
                if price is None or price <= 0:
                    continue
                t = datetime.fromisoformat(sample['at'].replace('Z', '+00:00'))
                if t.tzinfo is not None:
                    observed.append((t, price))
            observed.sort()
            if len(observed) < 4:
                continue
            # Use the latest three pattern samples as the decision point;
            # only strictly later observations can be outcomes.
            end = datetime.fromisoformat(item['sample_times'][-1])
            basis = next((price for t, price in observed if t == end), None)
            if basis is None:
                continue
            for horizon in minutes:
                eligible = [(abs((t-end).total_seconds()-horizon*60), price)
                            for t, price in observed if t > end and
                            abs((t-end).total_seconds()-horizon*60) <= tolerance_minutes*60]
                if not eligible:
                    continue
                price = min(eligible)[1]
                change = (price/basis-1)*100
                key = item['pattern'] + ':' + str(horizon) + 'm'
                outcomes[key]['evaluated'] += 1
                outcomes[key]['positive'] += int(change > 0)
                outcomes[key]['returns_pct'].append(round(change, 3))
        except (TypeError, ValueError, KeyError, AttributeError):
            continue
    return dict(outcomes)


def quality_summary(rows, history, patterns, outcomes, tracking_errors):
    """No synthetic fills, no return projections, and explicit coverage gaps."""
    rejected = diagnostics(rows)
    return {'pool_count': len(rows), 'eligible_now': sum(bool(r['watch']) for r in rows),
            'near_misses': rejected['near_miss_count'],
            'tracked_with_history': len(history), 'patterns_observed': len(patterns),
            'outcome_cohorts': {k: {'evaluated': v['evaluated'],
                                   'positive': v['positive']} for k, v in outcomes.items()},
            'tracking_errors': tracking_errors, 'gmgn_authenticated': False,
            'entry_fills': 0, 'exit_fills': 0,
            'paper_profit_eur': None, 'profitable_strategy_verified': False}


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
    tracked, tracking_errors = fetch_tracked(previous, {row['pool'] for row in rows})
    rows.extend(tracked)
    observed_at = datetime.now(timezone.utc).isoformat()
    history = history_update(previous, rows, observed_at)
    patterns = pattern_study(history)
    outcomes = pattern_outcomes(history, patterns)
    report = {'version': 'discovery-watch-r8', 'at': datetime.now(timezone.utc).isoformat(),
              'source': URL, 'status': status, 'snapshot_only': True,
              'not_trade_signals': True, 'watch_thresholds': {'liquidity_usd': WATCH_MIN_LIQUIDITY_USD, 'volume_5m_usd': WATCH_MIN_VOLUME_5M_USD, 'trades_5m': WATCH_MIN_TRADES_5M, 'max_gain_1h_pct': WATCH_MAX_GAIN_1H_PCT}, 'watch_count': sum(x['watch'] for x in rows), 'tracked_refreshed': len(tracked),
              'tracking_errors': tracking_errors, 'candidates': rows,
              'history': history, 'observed_performance': performance(history, (15, 30)),
              'pattern_study': patterns, 'pattern_outcomes': outcomes,
              'quality_summary': quality_summary(rows, history, patterns, outcomes, tracking_errors),
              'filter_diagnostics': diagnostics(rows)}
    with open('discovery_watch.json.tmp', 'w') as f: json.dump(report, f, allow_nan=False, indent=2)
    os.replace('discovery_watch.json.tmp', 'discovery_watch.json')
    print('DISCOVERY WATCH', status, len(rows), 'pools', report['watch_count'], 'watch candidates',
          'near_misses', report['filter_diagnostics']['near_miss_count'],
          'reasons', json.dumps(report['filter_diagnostics']['reason_counts'], sort_keys=True))
    return report


if __name__ == '__main__': run()

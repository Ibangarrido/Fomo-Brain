"""Isolated forward-only Kronos experiment. No wallet or order APIs."""
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from urllib.request import urlopen

SYMBOL = 'BTCUSDT'
HORIZON = 24
COST_BPS = 40  # total simulated round-trip fees + slippage

def read_candles():
    # Public market data only; exclude the current, unfinished candle.
    url = f'https://data-api.binance.vision/api/v3/klines?symbol={SYMBOL}&interval=1h&limit=512'
    with urlopen(url, timeout=30) as response:
        raw = json.load(response)
    now = int(time.time() * 1000)
    rows = [r for r in raw if r[6] < now]
    if len(rows) < 400 or now - rows[-1][6] > 2 * 3600000:
        raise ValueError('Insufficient or stale closed candles')
    for i, row in enumerate(rows):
        values = list(map(float, row[1:6]))
        if not all(math.isfinite(v) and v > 0 for v in values[:4]):
            raise ValueError('Invalid prices')
        if not math.isfinite(values[4]) or values[4] < 0:
            raise ValueError('Invalid volume')
        if i and row[0] - rows[i-1][0] != 3600000:
            raise ValueError('Candle gap')
    return rows

def settle(records, rows):
    prices = {int(r[6]) + 1: float(r[4]) for r in rows}
    for record in records:
        target = record['target_ms']
        if 'result' in record or target not in prices:
            continue
        # Entry is the observed quote at forecast publication, never a past close.
        actual = prices[target] / record['entry_price'] - 1
        record['result'] = {
            'exit_price': prices[target], 'market_return': actual,
            'direction_correct': (actual > 0) == (record['predicted_return'] > 0),
            'paper_net_return': actual - COST_BPS / 10000 if record['signal'] == 'LONG' else 0,
            'buy_hold_net_return': actual - COST_BPS / 10000,
            'settled_at_ms': int(time.time() * 1000),
        }

def main():
    import pandas as pd
    import torch
    from model import Kronos, KronosTokenizer, KronosPredictor
    output = Path(os.environ.get('KRONOS_STATE_DIR', 'kronos-state'))
    output.mkdir(exist_ok=True)
    path = output / 'ledger.json'
    seed = Path(__file__).parent / 'experiments/kronos/initial-ledger.json'
    records = json.loads(path.read_text()) if path.exists() else json.loads(seed.read_text())
    rows = read_candles()
    settle(records, rows)
    cutoff = int(rows[-1][6]) + 1
    key = f'{SYMBOL}:1h:{cutoff}:24:small-v1'
    if not any(r['id'] == key for r in records):
        torch.manual_seed(42)
        tokenizer = KronosTokenizer.from_pretrained('NeoQuasar/Kronos-Tokenizer-base', revision='0e0117387f39004a9016484a186a908917e22426')
        model = Kronos.from_pretrained('NeoQuasar/Kronos-small', revision='901c26c1332695a2a8f243eb2f37243a37bea320')
        predictor = KronosPredictor(model, tokenizer, device='cpu', max_context=512)
        data = pd.DataFrame([[float(r[i]) for i in (1,2,3,4,5,7)] for r in rows],
                            columns=['open','high','low','close','volume','amount'])
        x = pd.Series(pd.to_datetime([r[0] for r in rows], unit='ms'))
        y = pd.Series(pd.date_range(pd.Timestamp(cutoff, unit='ms'), periods=HORIZON, freq='h'))
        forecast = predictor.predict(df=data, x_timestamp=x, y_timestamp=y,
                                     pred_len=HORIZON, T=1.0, top_p=0.9, sample_count=1)
        predicted = float(forecast.iloc[-1]['close'])
        with urlopen(f'https://data-api.binance.vision/api/v3/ticker/price?symbol={SYMBOL}', timeout=30) as response:
            entry = float(json.load(response)['price'])
        published = int(time.time() * 1000)
        target = cutoff + HORIZON * 3600000
        if published >= target or not all(math.isfinite(v) and v > 0 for v in (entry, predicted)):
            raise ValueError('Invalid forecast or publication time')
        predicted_return = predicted / entry - 1
        records.append({'id': key, 'mode':'PAPER_ONLY', 'symbol':SYMBOL,
            'model':'NeoQuasar/Kronos-small', 'seed':42, 'sample_count':1,
            'created_at_ms':published, 'input_cutoff_ms':cutoff, 'target_ms':target,
            'input_sha256':hashlib.sha256(json.dumps(rows).encode()).hexdigest(),
            'entry_price':entry, 'predicted_close':predicted, 'predicted_return':predicted_return,
            'signal':'LONG' if predicted_return > COST_BPS / 10000 else 'CASH',
            'cost_bps':COST_BPS, 'virtual_notional_eur':10,
            'note':'Independent overlapping observations; not a funded portfolio or calibrated probability'})
        (output / f'input-{cutoff}.json').write_text(json.dumps(rows))
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(records, indent=2))
    temp.replace(path)
    print(json.dumps({'mode':'PAPER_ONLY','observations':len(records),
                      'settled':sum('result' in r for r in records),'latest':records[-1]}, indent=2))

if __name__ == '__main__':
    main()

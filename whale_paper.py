"""Read-only public demo alerts; independent, forward-only virtual experiment."""
import json
import math
import os
import signal
import time
import urllib.parse
from datetime import datetime, timezone
import fomo_brain as brain

FILE = 'fomo_paper_whale.json'
TRADER = 'FartmanSacks'
# App alerts are provider reports, not transaction receipts or verified wallet attribution.
URL = 'wss://api.fomoapi.io/ws/alerts?' + urllib.parse.urlencode({'trader': TRADER})
CHAIN_IDS = {4663: 'robinhood', 1399811149: 'solana', 1: 'ethereum', 56: 'bsc', 8453: 'base'}
BUY_FACTOR = 1 + brain.PAPER_FEE + brain.PAPER_SLIPPAGE
SELL_FACTOR = 1 - brain.PAPER_FEE - brain.PAPER_SLIPPAGE
STOP = False


def stamp(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def load():
    try:
        with open(FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {'version': 'WHALE DEMO r1', 'trader': TRADER, 'cash': 100.0,
                'realized': 0.0, 'positions': [], 'closed': [], 'events': [], 'seen': []}


def save(state):
    state['events'] = state['events'][-1000:]
    state['seen'] = state['seen'][-10000:]
    state['closed'] = state['closed'][-1000:]
    with open(FILE + '.tmp', 'w') as f:
        json.dump(state, f, indent=2, allow_nan=False)
    os.replace(FILE + '.tmp', FILE)


def normalize(msg, now, started):
    if (not isinstance(msg, dict) or msg.get('type') != 'alert'
            or msg.get('source') != 'feed'
            or str(msg.get('trader') or '').casefold() != TRADER.casefold()
            or msg.get('alertType') not in ('buy', 'sell')):
        return None, 'no es compra/venta del perfil seleccionado'
    try:
        ts = float(msg['ts']) / 1000  # Published schema: epoch milliseconds.
        chain_id = int(msg['chainId'])
    except (ValueError, TypeError, KeyError):
        return None, 'hora/cadena ausente o invalida'
    if not math.isfinite(ts) or ts < started or not 0 <= now - ts <= 180:
        return None, 'replay previo al inicio, antigua (>180s) o futura'
    chain = CHAIN_IDS.get(chain_id)
    address = msg.get('tokenAddress')
    if not chain or not isinstance(address, str) or not address.strip():
        return None, 'cadena sin soporte o contrato ausente'
    if not msg.get('eventId') or not msg.get('userId'):
        return None, 'faltan ids estables'
    return {'id': str(msg['eventId']), 'user_id': str(msg['userId']),
            'chain': chain, 'address': address, 'symbol': str(msg.get('token') or address),
            'side': msg['alertType'], 'source_at': stamp(ts), 'received_at': stamp(now),
            'delay_seconds': now-ts, 'source': 'fomoapi-unofficial-demo',
            'transaction_verified': False}, None


def quote(event):
    brain.JSON_CACHE.clear()
    pairs = [p for p in brain.pares_token(event['chain'], event['address'])
             if brain.numero(p.get('priceUsd')) > 0
             and brain.numero((p.get('liquidity') or {}).get('usd')) >= 10000]
    if not pairs:
        raise ValueError('sin precio/liquidez >=10000 USD del contrato exacto')
    p = max(pairs, key=lambda p: brain.numero((p.get('liquidity') or {}).get('usd')))
    return brain.numero(p['priceUsd']), p['pairAddress']


def close(state, pos, price, now, reason):
    proceeds = pos['quantity'] * price * SELL_FACTOR
    pnl = proceeds - pos['cost']
    state['cash'] += proceeds
    state['realized'] += pnl
    state['closed'].append({**pos, 'exit_at': stamp(now), 'exit_price': price,
                            'net_pnl': pnl, 'reason': reason})
    state['positions'].remove(pos)
    print(f"WHALE VIRTUAL SALIDA {pos['symbol']} | {stamp(now)} | neto={pnl:+.2f} EUR | {reason}", flush=True)


def process(state, event, now, quoter=quote):
    if event['id'] in state['seen']:
        return
    state['seen'].append(event['id'])
    state['events'].append(event)
    if state.get('user_id') and state['user_id'] != event['user_id']:
        event['result'] = 'DESCARTE: id de usuario distinto; posible cambio de perfil'
        return
    state['user_id'] = event['user_id']
    pos = next((p for p in state['positions']
                if (p['chain'], p['address']) == (event['chain'], event['address'])), None)
    if event['side'] == 'sell' and pos is None:
        event['result'] = 'DESCARTE: venta sin posicion propia'
        return
    if event['side'] == 'buy' and (pos or len(state['positions']) >= 3
                                  or state['cash'] < 10 or state.get('stale_positions', 0)):
        event['result'] = 'DESCARTE: duplicado/cupo/caja/cotizacion pendiente'
        return
    try:
        price, pool = quoter(event)
    except Exception as exc:
        event['result'] = 'DESCARTE: cotizacion no verificable (' + type(exc).__name__ + ')'
        return
    if quoter is quote:
        now = time.time()  # Our quote arrival, never the whale's historical fill.
    event['quoted_at'] = stamp(now)
    if event['side'] == 'sell':
        # This is an explicitly modeled full exit, not the whale's fraction or PnL.
        close(state, pos, price, now, 'alerta SELL: cierre completo modelado')
        event['result'] = 'SALIDA VIRTUAL'
    else:
        state['cash'] -= 10
        state['positions'].append({**event, 'pair': pool, 'entry_at': stamp(now),
                                   'entry_price': price, 'quantity': 10 / (price * BUY_FACTOR),
                                   'cost': 10.0, 'peak': price, 'mark_net': 10 * SELL_FACTOR / BUY_FACTOR,
                                   'quote_at': stamp(now), 'quote_ok': True})
        event['result'] = 'ENTRADA VIRTUAL'
        print(f"WHALE VIRTUAL ENTRADA {event['symbol']} | {stamp(now)} | precio={price} | retraso={event['delay_seconds']:.0f}s | 10 EUR", flush=True)


def mark(state, now, quoter=quote):
    for pos in list(state['positions']):
        try:
            price, pool = quoter(pos)
        except Exception:
            pos['quote_ok'] = False
            continue
        pos.update(pair=pool, mark_net=pos['quantity'] * price * SELL_FACTOR,
                   quote_at=stamp(now), quote_ok=True, peak=max(pos['peak'], price))
        pnl = pos['mark_net'] / pos['cost'] - 1
        if pnl <= -0.15:
            close(state, pos, price, now, 'stop neto -15% observado')
        elif pos['peak'] / pos['entry_price'] * SELL_FACTOR / BUY_FACTOR >= 1.30 and price <= pos['peak'] * 0.85:
            close(state, pos, price, now, 'trailing -15% tras beneficio neto observado +30%')
    state['stale_positions'] = sum(not p.get('quote_ok') for p in state['positions'])
    state['last_accounting_equity'] = state['cash'] + sum(p['mark_net'] for p in state['positions'])
    state['equity_verified'] = state['stale_positions'] == 0
    for pos in state['positions']:
        print(f"WHALE POSICION {pos['symbol']} | {pos['chain']}:{pos['address']} | entrada={pos['entry_at']} | ultima cotizacion={pos['quote_at']} | verificable={pos['quote_ok']}", flush=True)
    print(f"WHALE DEMO | patrimonio contable={state['last_accounting_equity']:.2f} EUR | verificable={state['equity_verified']} | realizado={state['realized']:+.2f} | abiertas={len(state['positions'])} | eventos={len(state['events'])}", flush=True)


def run(seconds=900):
    import websocket  # Only the read-only watcher requires this dependency.
    global STOP
    signal.signal(signal.SIGTERM, lambda *_: globals().__setitem__('STOP', True))
    state = load()
    started = time.time()
    deadline = time.monotonic() + seconds
    next_mark = 0
    ws = None
    next_connect = 0
    print('WHALE DEMO r1 | FartmanSacks | cartera independiente 100 EUR virtuales | proveedor no oficial; sin verificacion de tx | demo ~60s de retraso', flush=True)
    try:
        while not STOP and time.monotonic() < deadline:
            now = time.time()
            if now >= next_mark:
                mark(state, now)
                save(state)
                next_mark = now + 60
            if ws is None:
                if now < next_connect:
                    time.sleep(1)
                    continue
                try:
                    ws = websocket.create_connection(URL, timeout=5)
                    ws.settimeout(1)
                    state['feed_status'] = 'CONECTADO; esperando alertas'
                    print('WHALE FEED: CONECTADO (no implica operaciones)', flush=True)
                except Exception as exc:
                    state['feed_status'] = 'NO DISPONIBLE: ' + type(exc).__name__
                    print('WHALE FEED: ' + state['feed_status'], flush=True)
                    next_connect = now + 30
                    save(state)
                    continue
            try:
                msg = json.loads(ws.recv())
                if msg.get('type') == 'welcome':
                    state['provider_delay_seconds'] = msg.get('delaySeconds')
                    print('WHALE FEED welcome: ' + json.dumps({k: msg.get(k) for k in ('realtime', 'delaySeconds')}), flush=True)
                event, reason = normalize(msg, time.time(), started)
                if event:
                    process(state, event, time.time())
                    print(f"WHALE ALERTA {event['symbol']} {event['side']} | {event.get('result', 'duplicada')} | tx NO verificada", flush=True)
                    save(state)
                elif msg.get('type') == 'alert':
                    state['rejected_alerts'] = state.get('rejected_alerts', 0) + 1
                    print('WHALE DESCARTE: ' + str(reason), flush=True)
            except websocket.WebSocketTimeoutException:
                pass
            except Exception as exc:
                state['feed_status'] = 'DESCONECTADO: ' + type(exc).__name__
                print('WHALE FEED: ' + state['feed_status'], flush=True)
                ws.close()
                ws = None
                next_connect = time.time() + 30
    finally:
        if ws:
            ws.close()
        mark(state, time.time())
        state['watcher_status'] = 'SESION FINALIZADA'
        save(state)
        print('WHALE FIN: observacion solo durante esta run; huecos entre runs. Costes 1%+2% por lado; FX 1:1; sin gas/MEV.', flush=True)


if __name__ == '__main__':
    run(int(os.getenv('WHALE_SECONDS', '900')))

"""Read-only public demo alerts; independent, forward-only virtual experiment."""
import json
import math
import os
import signal
import time
import urllib.parse
from datetime import datetime, timezone
import fomo_brain as brain

TRADER = os.getenv('WHALE_TRADER', 'FartmanSacks').strip()
if TRADER not in ('FartmanSacks', 'unipcs'):
    raise ValueError('Perfil no configurado para esta prueba')
FILE = 'fomo_paper_whale.json' if TRADER == 'FartmanSacks' else 'fomo_paper_whale_unipcs.json'
# App alerts are provider reports, not transaction receipts or verified wallet attribution.
URL = 'wss://api.fomoapi.io/ws/alerts?' + urllib.parse.urlencode({'trader': TRADER})
CHAIN_IDS = {4663: 'robinhood', 1399811149: 'solana', 1: 'ethereum', 56: 'bsc', 8453: 'base'}
BUY_FACTOR = (1 + brain.PAPER_FEE) * (1 + brain.PAPER_SLIPPAGE)
SELL_FACTOR = (1 - brain.PAPER_FEE) * (1 - brain.PAPER_SLIPPAGE)
GECKO = 'https://api.geckoterminal.com/api/v2/networks/robinhood'
STOP = False
GECKO_CALLS = []


def stamp(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def load():
    try:
        with open(FILE) as f:
            state = json.load(f)
        if state.get('trader') != TRADER:
            raise ValueError('El estado pertenece a otro perfil; no se mezclan carteras')
        state.setdefault('reserve', 0.0)
        state['version'] = 'WHALE DEMO r2'
        return state
    except FileNotFoundError:
        return {'version': 'WHALE DEMO r2', 'trader': TRADER, 'cash': 100.0, 'reserve': 0.0,
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
            'reported_usd_value': msg.get('usdValue'),
            'transaction_verified': False}, None


def gecko_json(url):
    # Two readers share an IP: <=10 requests/min each, below public 30/min.
    now = time.monotonic()
    GECKO_CALLS[:] = [ts for ts in GECKO_CALLS if now-ts < 60]
    if len(GECKO_CALLS) >= 10:
        raise ValueError('GeckoTerminal: presupuesto de 10 consultas/min agotado')
    GECKO_CALLS.append(now)
    return brain.pedir_json(url)


def gecko_pool(payload, address):
    """Select exact token side; never price WETH instead of the requested coin."""
    valid = []
    expected = ('robinhood_' + address).lower()
    for p in payload.get('data') or []:
        if not str(p.get('id', '')).startswith('robinhood_'):
            continue
        a = p.get('attributes') or {}
        rel = p.get('relationships') or {}
        side = next((s for s in ('base_token', 'quote_token')
                     if str(((rel.get(s) or {}).get('data') or {}).get('id', '')).lower() == expected), None)
        if side is None or not a.get('address'):
            continue
        price = brain.numero(a.get(side + '_price_usd'))
        liquidity = brain.numero(a.get('reserve_in_usd'))
        if math.isfinite(price) and math.isfinite(liquidity) and price > 0 and liquidity >= 10000:
            valid.append((liquidity, price, a['address']))
    if not valid:
        raise ValueError('GeckoTerminal: sin pool del contrato exacto con precio y liquidez >=10000 USD')
    liquidity, price, pool = max(valid)
    return price, pool, liquidity


def candle_context(payload, now):
    """Only completed 1m OHLCV bars, never sampled quotes presented as candles."""
    rows = []
    for row in ((payload.get('data') or {}).get('attributes') or {}).get('ohlcv_list') or []:
        if not isinstance(row, list) or len(row) < 6:
            continue
        try:
            ts, o, h, low, c, vol = map(float, row[:6])
        except (ValueError, TypeError):
            continue
        if (all(math.isfinite(x) for x in (ts, o, h, low, c, vol))
                and 0 < low <= min(o, c) <= max(o, c) <= h and vol >= 0
                and ts + 60 <= now and now - ts <= 600):
            rows.append([ts, o, h, low, c, vol])
    rows.sort(key=lambda r: r[0])
    if not rows:
        return {'status': 'SIN VELAS CERRADAS RECIENTES'}
    ts, o, h, low, c, vol = rows[-1]
    return {'status': 'OHLCV 1m cerrada; contexto, no regla de entrada',
            'last_bar_at': stamp(ts), 'last_bar_age_seconds': now-ts,
            'stale': now-ts > 180, 'bars': rows[-5:],
            'body_pct': (c/o-1)*100,
            'upper_wick_fraction': (h-max(o,c))/(h-low) if h>low else 0,
            'volume_usd': vol}


def peer_buys(event, now):
    """Reported simultaneous buying is correlation, not proof of communication."""
    peer_file = 'fomo_paper_whale_unipcs.json' if TRADER == 'FartmanSacks' else 'fomo_paper_whale.json'
    try:
        with open(peer_file) as f:
            peer = json.load(f)
        expected = 'unipcs' if TRADER == 'FartmanSacks' else 'FartmanSacks'
        if peer.get('trader') != expected or peer.get('user_id') == event['user_id']:
            return []
        for e in reversed(peer.get('events', [])):
            if (e.get('side') == 'buy' and e.get('chain') == event['chain']
                    and (e.get('address') == event['address'] if event['chain'] == 'solana' else str(e.get('address', '')).lower() == event['address'].lower())):
                ts = datetime.fromisoformat(e['source_at']).timestamp()
                own_ts = datetime.fromisoformat(event['source_at']).timestamp()
                if 0 <= now-ts <= 180 and abs(own_ts-ts) <= 180:
                    return [expected]
        return []
    except (OSError, ValueError, KeyError, TypeError):
        return []


def quote(event):
    brain.JSON_CACHE.clear()
    try:
        raw = brain.pares_token(event['chain'], event['address'])
        event['dex_coverage'] = 'pares recibidos=' + str(len(raw))
    except Exception as exc:
        raw = []
        event['dex_coverage'] = 'error=' + type(exc).__name__
    pairs = [p for p in raw
             if brain.numero(p.get('priceUsd')) > 0
             and brain.numero((p.get('liquidity') or {}).get('usd')) >= 10000]
    if not pairs:
        if event['chain'] != 'robinhood':
            raise ValueError('DEX: sin mercado admisible; ' + event['dex_coverage'])
        address = urllib.parse.quote(event['address'], safe='')
        data = gecko_json(GECKO + '/tokens/' + address + '/pools')
        price, pool, liquidity = gecko_pool(data, event['address'])
        event.update(quote_source='geckoterminal', quote_liquidity_usd=liquidity)
        return price, pool
    p = max(pairs, key=lambda p: brain.numero((p.get('liquidity') or {}).get('usd')))
    event.update(quote_source='dexscreener', quote_liquidity_usd=brain.numero((p.get('liquidity') or {}).get('usd')))
    return brain.numero(p['priceUsd']), p['pairAddress']


def close(state, pos, price, now, reason):
    proceeds = pos['quantity'] * price * pos.get('sell_factor', 0.97)
    pnl = proceeds - pos['cost']
    reserved = max(pnl, 0) * 0.5
    state['reserve'] = state.get('reserve', 0) + reserved
    state['cash'] += proceeds - reserved
    state['realized'] += pnl
    state['closed'].append({**pos, 'exit_at': stamp(now), 'exit_price': price,
                            'net_pnl': pnl, 'reserved': reserved, 'reason': reason})
    state['positions'].remove(pos)
    print(f"WHALE {TRADER} VIRTUAL SALIDA {pos['symbol']} | {stamp(now)} | neto={pnl:+.2f} EUR | {reason}", flush=True)


def process(state, event, now, quoter=quote):
    if event['id'] in state['seen']:
        return
    state['seen'].append(event['id'])
    state['events'].append(event)
    if state.get('user_id') and state['user_id'] != event['user_id']:
        event['result'] = 'DESCARTE: id de usuario distinto; posible cambio de perfil'
        return
    state['user_id'] = event['user_id']
    if event['side'] == 'buy':
        event['coincident_profiles'] = peer_buys(event, now)
        if event['coincident_profiles']:
            print(f"WHALE {TRADER} COINCIDENCIA BUY | {event['chain']}:{event['address']} | {event['coincident_profiles']} | <=180s; NO prueba de coordinacion ni tx verificada", flush=True)
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
        event['quote_error'] = str(exc)[:300]
        event['result'] = 'DESCARTE: cotizacion no verificable (' + type(exc).__name__ + '): ' + event['quote_error']
        return
    if quoter is quote:
        now = time.time()  # Our quote arrival, never the whale's historical fill.
    event['quoted_at'] = stamp(now)
    if event['side'] == 'sell':
        # This is an explicitly modeled full exit, not the whale's fraction or PnL.
        close(state, pos, price, now, 'alerta SELL: cierre completo modelado')
        event['result'] = 'SALIDA VIRTUAL'
    else:
        if event.get('quote_source') == 'geckoterminal':
            try:
                params = urllib.parse.urlencode({'aggregate': 1, 'limit': 6, 'currency': 'usd', 'token': event['address']})
                candles = gecko_json(GECKO + '/pools/' + urllib.parse.quote(pool, safe='') + '/ohlcv/minute?' + params)
                event['candle_context'] = candle_context(candles, time.time())
                print(f"WHALE {TRADER} VELAS 1m | {event['chain']}:{event['address']} | " + json.dumps(event['candle_context']), flush=True)
            except Exception as exc:
                event['candle_context'] = {'status': 'NO DISPONIBLE: ' + type(exc).__name__}
        state['cash'] -= 10
        state['positions'].append({**event, 'pair': pool, 'entry_at': stamp(now),
                                   'entry_price': price, 'quantity': 10 / (price * BUY_FACTOR),
                                   'buy_factor': BUY_FACTOR, 'sell_factor': SELL_FACTOR,
                                   'cost': 10.0, 'peak': price, 'mark_net': 10 * SELL_FACTOR / BUY_FACTOR,
                                   'quote_at': stamp(now), 'quote_ok': True})
        event['result'] = 'ENTRADA VIRTUAL'
        print(f"WHALE {TRADER} VIRTUAL ENTRADA {event['symbol']} | {stamp(now)} | precio={price} | retraso={event['delay_seconds']:.0f}s | 10 EUR", flush=True)


def mark(state, now, quoter=quote):
    for pos in list(state['positions']):
        try:
            price, pool = quoter(pos)
        except Exception:
            pos['quote_ok'] = False
            continue
        pos.update(pair=pool, mark_net=pos['quantity'] * price * pos.get('sell_factor', 0.97),
                   quote_at=stamp(now), quote_ok=True, peak=max(pos['peak'], price))
        pnl = pos['mark_net'] / pos['cost'] - 1
        if pnl <= -0.15:
            close(state, pos, price, now, 'stop neto -15% observado')
        elif pos['peak'] / pos['entry_price'] * pos.get('sell_factor', 0.97) / pos.get('buy_factor', 1.03) >= 1.30 and price <= pos['peak'] * 0.85:
            close(state, pos, price, now, 'trailing -15% tras beneficio neto observado +30%')
    state['stale_positions'] = sum(not p.get('quote_ok') for p in state['positions'])
    state['last_accounting_equity'] = state['cash'] + state.get('reserve', 0) + sum(p['mark_net'] for p in state['positions'])
    state['equity_verified'] = state['stale_positions'] == 0
    for pos in state['positions']:
        print(f"WHALE {TRADER} POSICION {pos['symbol']} | {pos['chain']}:{pos['address']} | entrada={pos['entry_at']} | ultima cotizacion={pos['quote_at']} | verificable={pos['quote_ok']}", flush=True)
    print(f"WHALE {TRADER} CAJA | disponible={state['cash']:.2f} EUR | reserva={state.get('reserve', 0):.2f} EUR", flush=True)
    print(f"WHALE {TRADER} DEMO | patrimonio contable={state['last_accounting_equity']:.2f} EUR | verificable={state['equity_verified']} | realizado={state['realized']:+.2f} | abiertas={len(state['positions'])} | eventos={len(state['events'])}", flush=True)


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
    print(f'WHALE DEMO r2 | {TRADER} | cartera independiente 100 EUR virtuales | proveedor no oficial; sin verificacion de tx | demo ~60s de retraso', flush=True)
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
                    print(f'WHALE {TRADER} FEED: CONECTADO (no implica operaciones)', flush=True)
                except Exception as exc:
                    state['feed_status'] = 'NO DISPONIBLE: ' + type(exc).__name__
                    print(f'WHALE {TRADER} FEED: ' + state['feed_status'], flush=True)
                    next_connect = now + 30
                    save(state)
                    continue
            try:
                msg = json.loads(ws.recv())
                if msg.get('type') == 'welcome':
                    state['provider_delay_seconds'] = msg.get('delaySeconds')
                    print(f'WHALE {TRADER} FEED welcome: ' + json.dumps({k: msg.get(k) for k in ('realtime', 'delaySeconds')}), flush=True)
                event, reason = normalize(msg, time.time(), started)
                if event:
                    process(state, event, time.time())
                    print(f"WHALE {TRADER} ALERTA {event['symbol']} {event['side']} | {event['chain']}:{event['address']} | fuente={event.get('quote_source', 'sin cotizacion')} | {event.get('result', 'duplicada')} | tx NO verificada", flush=True)
                    save(state)
                elif msg.get('type') == 'alert':
                    state['rejected_alerts'] = state.get('rejected_alerts', 0) + 1
                    print(f'WHALE {TRADER} DESCARTE: ' + str(reason), flush=True)
            except websocket.WebSocketTimeoutException:
                pass
            except Exception as exc:
                state['feed_status'] = 'DESCONECTADO: ' + type(exc).__name__
                print(f'WHALE {TRADER} FEED: ' + state['feed_status'], flush=True)
                ws.close()
                ws = None
                next_connect = time.time() + 30
    finally:
        if ws:
            ws.close()
        mark(state, time.time())
        state['watcher_status'] = 'SESION FINALIZADA'
        save(state)
        print(f'WHALE {TRADER} FIN: observacion solo durante esta run; huecos entre runs. Costes 1%+2% por lado; FX 1:1; sin gas/MEV.', flush=True)


if __name__ == '__main__':
    run(int(os.getenv('WHALE_SECONDS', '900')))

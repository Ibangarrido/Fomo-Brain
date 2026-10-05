import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('brain', os.path.join(os.path.dirname(__file__), 'fomo_brain.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def pair(address='a', pool='p', liquidity=20000, price=1):
    return {'chainId': 'solana', 'pairAddress': pool, 'baseToken': {'address': address, 'symbol': 'TEST'},
            'priceUsd': str(price), 'marketCap': 100000, 'liquidity': {'usd': liquidity},
            'volume': {'h1': 15000, 'm5': 3000}, 'priceChange': {'h1': 20, 'm5': 5},
            'txns': {'m5': {'buys': 35, 'sells': 10}},
            'pairCreatedAt': int((datetime.now(timezone.utc)-timedelta(minutes=30)).timestamp()*1000)}


class V10Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.temp.name)
        b.JSON_CACHE.clear()
        b.REJECTIONS.clear()
    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()
    def quote(self, old, alternatives):
        with patch.object(b, 'pedir_json', return_value={'pairs': old}), patch.object(b, 'pares_token', return_value=alternatives):
            pos = {'chain': 'solana', 'address': 'a', 'pair': 'old'}
            result = b.cotizar_posicion(pos)
            return pos, result
    def test_contract_identity_and_migration(self):
        bad = pair('impostor', 'fake', 1000000)
        wrongchain = pair('a', 'wrong', 2000000)
        wrongchain['chainId'] = 'bsc'
        pos, (price, liquidity, p) = self.quote([pair(pool='old', liquidity=0)], [bad, wrongchain, pair(pool='new')])
        self.assertEqual(pos['pair'], 'new')
        self.assertEqual(len(pos['pair_history']), 1)
        self.assertEqual(liquidity, 20000)
    def test_no_pool_does_not_fabricate_sale(self):
        with self.assertRaises(ValueError):
            self.quote([], [pair('other')])

    def test_low_liquidity_reports_price_without_sale_or_new_entry(self):
        t = b.analizar_par(pair())
        with patch.object(b, 'cotizar_posicion', return_value=(1, 20000, pair())):
            b.simular_cartera([t], confirm=False)
        with open(b.V10_FILE) as handle:
            before = json.load(handle)
        with patch.object(b, 'pedir_json', return_value={'pairs': [pair(liquidity=8000, price=.5)]}), \
             patch.object(b, 'pares_token', return_value=[]):
            b.simular_cartera([b.analizar_par(pair(address='second'))])
        with open(b.V10_FILE) as handle:
            low = json.load(handle)
        pos = low['positions'][0]
        self.assertEqual(low['cash'], 90)
        self.assertEqual(low['reserve'], 0)
        self.assertEqual(low['closed'], [])
        self.assertEqual(len(low['seen']), 1)
        self.assertEqual(pos['mark_net'], before['positions'][0]['mark_net'])
        self.assertEqual(pos['last_quote_at'], before['positions'][0]['last_quote_at'])
        self.assertEqual(pos['quote_status'], 'NO VERIFICABLE')
        self.assertEqual(pos['indicative_price'], .5)
        self.assertLess(pos['indicative_pnl_pct'], -15)
        self.assertAlmostEqual(low['observations'][-1]['indicative_only_equity'],
                               90 + pos['indicative_mark_net'])
        self.assertEqual(low['observations'][-1]['verified_component'], 90)
        self.assertFalse(low['observations'][-1]['valuation_complete'])
        # Un error posterior no puede presentar el precio indicativo anterior como actual.
        with patch.object(b, 'cotizar_posicion', side_effect=ValueError('sin precio')):
            b.simular_cartera([])
        with open(b.V10_FILE) as handle:
            missing = json.load(handle)
        self.assertNotIn('indicative_price', missing['positions'][0])
        self.assertIsNone(missing['observations'][-1]['indicative_only_equity'])
        self.assertEqual(missing['closed'], [])
        # Solo al recuperar una cotizacion admitida se procesa la salida virtual.
        with patch.object(b, 'cotizar_posicion', return_value=(.5, 20000, pair(price=.5))):
            b.simular_cartera([])
        with open(b.V10_FILE) as handle:
            recovered = json.load(handle)
        self.assertEqual(recovered['positions'], [])
        self.assertEqual(recovered['closed'][0]['exit_reason'], 'STOP -15%')
        self.assertNotIn('indicative_price', recovered['closed'][0])

    def test_indicative_price_survives_fallback_outage_and_checks_identity(self):
        pos = {'chain': 'solana', 'address': 'a', 'pair': 'p'}
        with patch.object(b, 'pedir_json', return_value={'pairs': [pair(liquidity=8000, price=.5)]}), \
             patch.object(b, 'pares_token', side_effect=ValueError('endpoint caido')):
            with self.assertRaises(b.CotizacionBajaLiquidez) as error:
                b.cotizar_posicion(pos)
        self.assertEqual(error.exception.price, .5)
        self.assertEqual(error.exception.liquidity, 8000)
        with patch.object(b, 'pedir_json', return_value={'pairs': [pair(address='impostor', liquidity=8000, price=.5)]}), \
             patch.object(b, 'pares_token', return_value=[]):
            with self.assertRaises(ValueError) as invalid:
                b.cotizar_posicion(pos)
        self.assertNotIsInstance(invalid.exception, b.CotizacionBajaLiquidez)
    def test_discovery_metrics_and_rejections(self):
        t = b.analizar_par(pair())
        self.assertEqual(t['netTrades5m'], 25)
        self.assertEqual(t['volumeLiquidity1h'], .75)
        self.assertEqual(t['graduationStatus'], 'NO VERIFICADA')
        self.assertIsNone(b.analizar_par(pair(liquidity=2)))
        self.assertIn('liquidez', b.REJECTIONS[-1]['reason'])
    def test_confirmation_requires_same_recent_pool(self):
        t = b.analizar_par(pair())
        self.assertIn('falta lectura', b.motivo_entrada(t, True))
        old = dict(t, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(), price=.95, liquidity=19000, vol5m=2000)
        with open(b.MEMORY_FILE, 'w') as f:
            json.dump([old], f)
        self.assertIsNone(b.motivo_entrada(t, True))
        old['pair'] = 'different'
        with open(b.MEMORY_FILE, 'w') as f:
            json.dump([old], f)
        self.assertIn('falta lectura', b.motivo_entrada(t, True))
    def test_v9_preserves_state_and_tracks_stop(self):
        t = b.analizar_par(pair())
        with patch.object(b, 'cotizar_posicion', return_value=(1, 20000, pair())):
            b.simular_cartera([t], confirm=False)
        with open(b.V10_FILE) as f:
            s = json.load(f)
        self.assertEqual(s['cash'], 90)
        with patch.object(b, 'cotizar_posicion', side_effect=ValueError('sin liquidez')):
            b.simular_cartera([b.analizar_par(pair('second'))], confirm=False)
        with open(b.V10_FILE) as f:
            stale = json.load(f)
        self.assertEqual(stale['cash'], 90)
        self.assertEqual(stale['closed'], [])
        self.assertFalse(stale['observations'][-1]['valuation_complete'])
        with patch.object(b, 'cotizar_posicion', return_value=(.5, 20000, pair(price=.5))):
            b.simular_cartera([])
        with open(b.V10_FILE) as f:
            stopped = json.load(f)
        self.assertEqual(stopped['positions'], [])
        self.assertLess(stopped['closed'][0]['profit'], 0)
        with patch.object(b, 'cotizar_posicion', return_value=(1, 20000, pair())):
            b.simular_cartera([], 'isolated_test.json', 'AISLADA', True)
        with open(b.V10_FILE) as f:
            self.assertEqual(json.load(f), stopped)
    def test_study_not_auto_purchased(self):
        t = b.analizar_par(pair(b.STUDY_TOKENS[0][1]))
        with patch.object(b, 'cotizar_posicion') as quote:
            b.simular_cartera([t], confirm=False)
            quote.assert_not_called()
        with open(b.V10_FILE) as f:
            self.assertEqual(json.load(f)['cash'], 100)

    def test_partial_profit_reserve_and_trailing(self):
        t = b.analizar_par(pair())
        with patch.object(b, 'cotizar_posicion', return_value=(1, 20000, pair())):
            b.simular_cartera([t], confirm=False)
        with patch.object(b, 'cotizar_posicion', return_value=(1.5, 20000, pair(price=1.5))):
            b.simular_cartera([])
        with open(b.V10_FILE) as f:
            s = json.load(f)
        self.assertEqual(len(s['positions']), 1)
        self.assertTrue(s['positions'][0]['partial_taken'])
        self.assertEqual(s['positions'][0]['budget'], 5)
        self.assertEqual(s['closed'][0]['exit_reason'], 'PARCIAL +30%')
        self.assertAlmostEqual(s['reserve'], s['closed'][0]['profit'] * .5)
        with patch.object(b, 'cotizar_posicion', return_value=(1.2, 20000, pair(price=1.2))):
            b.simular_cartera([])
        with open(b.V10_FILE) as f:
            end = json.load(f)
        self.assertEqual(end['positions'], [])
        self.assertEqual(end['closed'][-1]['exit_reason'], 'TRAILING -15%')
        self.assertAlmostEqual(end['observations'][-1]['estimated_equity'] - 100,
                               sum(x['profit'] for x in end['closed']))

    def test_v9_default_requires_confirmation_and_uses_v9_file(self):
        t = b.analizar_par(pair())
        with patch.object(b, 'cotizar_posicion', return_value=(1, 20000, pair())):
            b.simular_cartera([t])
        with open(b.V10_FILE) as f:
            self.assertEqual(json.load(f)['cash'], 100)
        old = dict(t, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                   price=.95, liquidity=19000, vol5m=2000)
        with open(b.MEMORY_FILE, 'w') as f:
            json.dump([old], f)
        with patch.object(b, 'cotizar_posicion', return_value=(1, 20000, pair())):
            b.simular_cartera([t])
        with open(b.V10_FILE) as f:
            state = json.load(f)
        self.assertEqual(state['cash'], 90)
        self.assertEqual(state['assumptions']['strategy'], 'confirmacion V10')

    def test_learning_entry_limits(self):
        t = b.analizar_par(pair())
        t.update(trades5m=40, buyRatio5m=.60, ageMinutes=30,
                 liquidity=20000, vol5m=3000)
        old = dict(t, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                   price=.95, liquidity=21000, vol5m=3000)
        with patch.object(b, 'cargar_memoria', return_value=[old]):
            self.assertIsNone(b.motivo_entrada(t, True))
            for field, value in [('trades5m', 39), ('buyRatio5m', .59),
                                 ('ageMinutes', 61), ('change5m', 61),
                                 ('liquidity', 19000), ('vol5m', 2999),
                                 ('price', .94)]:
                with self.subTest(field=field):
                    rejected = dict(t, **{field: value})
                    self.assertIsNotNone(b.motivo_entrada(rejected, True))

    def test_early_rejects_fading_volume_rebound_and_price_jump(self):
        t = b.analizar_par(pair())
        old = dict(t, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                   price=.95, vol5m=3000)
        with patch.object(b, 'cargar_memoria', return_value=[old]):
            self.assertIsNone(b.motivo_entrada(t, True))
            self.assertIn('volumen5m decreciente', b.motivo_entrada(dict(t, vol5m=2000), True))
            self.assertIn('1-12%', b.motivo_entrada(dict(t, price=1.1), True))
        with patch.object(b, 'cargar_memoria', return_value=[dict(old, change5m=-20)]):
            self.assertIn('sostenido', b.motivo_entrada(t, True))

    def test_fresh_quote_drift_rejects_without_spending_and_records_accepted_snapshot(self):
        t = b.analizar_par(pair())
        old = dict(t, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                   price=.95, vol5m=2000)
        with patch.object(b, 'cargar_memoria', return_value=[old]):
            with patch.object(b, 'cotizar_posicion', return_value=(1.06, 20000, pair(price=1.06))):
                b.simular_cartera([t])
            with open(b.V10_FILE) as f:
                rejected = json.load(f)
            self.assertEqual(rejected['cash'], 100)
            self.assertEqual(rejected['positions'], [])
            self.assertIn('cotizacion se aleja', rejected['last_run_notes'][0])
            with patch.object(b, 'cotizar_posicion', return_value=(1.01, 20000, pair(price=1.01))):
                b.simular_cartera([t])
        with open(b.V10_FILE) as f:
            accepted = json.load(f)
        self.assertEqual(accepted['cash'], 90)
        pos = accepted['positions'][0]
        self.assertEqual(float(pos['entry_snapshot']['price']), 1.01)
        self.assertEqual(pos['entry_policy_version'], 'early-r4')
        self.assertEqual(pos['entry_confirmation']['hora'], old['hora'])
        self.assertEqual(pos['entry_confirmation']['price'], .95)
        self.assertAlmostEqual(pos['quote_drift_pct'], 1)
        self.assertEqual(float(pos['signal_price']), 1)

    def test_early_allows_hourly_pump_but_requires_recent_confirmation(self):
        t = b.analizar_par(pair())
        t['change1h'] = 500
        old = dict(t, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                   price=.95, liquidity=19000, vol5m=2000)
        with patch.object(b, 'cargar_memoria', return_value=[old]):
            self.assertIsNone(b.motivo_entrada(t, True))
            self.assertIsNotNone(b.motivo_entrada(dict(t, ageMinutes=1), True))
            self.assertIsNotNone(b.motivo_entrada(dict(t, change5m=1), True))
        old['hora'] = (datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
        with patch.object(b, 'cargar_memoria', return_value=[old]):
            self.assertIsNotNone(b.motivo_entrada(t, True))

    def test_impulse_requires_growth_and_allows_old_pairs(self):
        t = b.analizar_par(pair())
        t['ageMinutes'] = 90 * 24 * 60
        old = dict(t, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                   price=.95, liquidity=19000, vol5m=2000)
        with patch.object(b, 'cargar_memoria', return_value=[old]):
            self.assertIsNotNone(b.motivo_entrada(t, True, 'early'))
            self.assertIsNone(b.motivo_entrada(t, True, 'impulse'))
            for field, value in [('price', .95), ('price', 1.2), ('vol5m', 2100),
                                 ('liquidity', 17000), ('buyRatio5m', .54)]:
                with self.subTest(field=field, value=value):
                    self.assertIsNotNone(b.motivo_entrada(dict(t, **{field: value}), True, 'impulse'))
        with patch.object(b, 'cargar_memoria', return_value=[]):
            self.assertIsNotNone(b.motivo_entrada(t, True, 'impulse'))

    def test_impulse_rejects_extended_five_minute_candle(self):
        token = dict(b.analizar_par(pair()), change5m=45.71, price=1.05,
                     vol5m=1200, liquidity=30000, trades5m=192, buyRatio5m=0.63)
        old = dict(token, change5m=12, price=1.0, vol5m=1000,
                   hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat())
        with patch.object(b, 'cargar_memoria', return_value=[old]):
            reason = b.motivo_entrada(token, True, 'impulse')
        self.assertIn('vela 5m extendida', reason)
        with patch.object(b, 'cargar_memoria', return_value=[old]):
            self.assertIsNone(b.motivo_entrada(dict(token, change5m=25), True, 'impulse'))
            self.assertIn('vela 5m extendida',
                          b.motivo_entrada(dict(token, change5m=25.01), True, 'impulse'))


    def test_impulse_wallet_is_separate_and_persists(self):
        t = b.analizar_par(pair())
        old = dict(t, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                   price=.95, liquidity=19000, vol5m=2000)
        with open(b.MEMORY_FILE, 'w') as f:
            json.dump([old], f)
        with patch.object(b, 'cotizar_posicion', return_value=(1, 20000, pair())):
            b.simular_cartera([t], b.V10_IMPULSE_FILE, 'IMPULSO', True, 'impulse')
            b.simular_cartera([], b.V10_IMPULSE_FILE, 'IMPULSO', True, 'impulse')
        with open(b.V10_IMPULSE_FILE) as f:
            state = json.load(f)
        self.assertEqual(state['cash'], 90)
        self.assertEqual(len(state['positions']), 1)
        self.assertEqual(len(state['observations']), 2)
        self.assertFalse(os.path.exists(b.V10_FILE))
        self.assertEqual(state['assumptions']['entry_mode'], 'impulse')

    def test_session_clears_cache_between_reads(self):
        b.JSON_CACHE['stale'] = {}
        with patch.object(b, 'main') as main, patch.object(b.time, 'sleep'), patch.object(b.time, 'monotonic', return_value=0):
            b.run_session(2)
            self.assertEqual(main.call_count, 2)
        self.assertEqual(b.JSON_CACHE, {})
        with self.assertRaises(ValueError):
            b.run_session(16)

    def test_confirmation_is_30_to_90_seconds_for_both_wallets(self):
        now = datetime.now(timezone.utc)
        t = b.analizar_par(pair())
        for seconds, accepted in [(29, False), (30, True), (90, True), (91, False), (120, False), (300, False)]:
            old = dict(t, hora=(now-timedelta(seconds=seconds)).isoformat(),
                       price=.95, vol5m=2000)
            with patch.object(b, 'datetime') as clock, patch.object(b, 'cargar_memoria', return_value=[old]):
                clock.now.return_value = now
                clock.fromisoformat.side_effect = datetime.fromisoformat
                for mode in ('early', 'impulse'):
                    with self.subTest(seconds=seconds, mode=mode):
                        reason = b.motivo_entrada(t, True, mode)
                        self.assertEqual(reason is None, accepted)

    def test_run130_entry_regressions_are_rejected_by_impulse_r2(self):
        t = b.analizar_par(pair())
        ore = dict(t, price=.0002593, liquidity=49114, trades5m=587,
                   buyRatio5m=.586, vol5m=42520, change5m=22.05)
        old = dict(ore, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                   price=.0002414, vol5m=36584)
        with patch.object(b, 'cargar_memoria', return_value=[old]):
            self.assertEqual(b.motivo_entrada(ore, True, 'impulse'), 'ratio compras < 60%')
        gang = dict(t, price=.00002518, liquidity=23206, trades5m=153,
                    buyRatio5m=.601, vol5m=8765, change5m=18.17)
        old = dict(gang, hora=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(),
                   price=.00002110, vol5m=6394)
        with patch.object(b, 'cargar_memoria', return_value=[old]):
            self.assertIn('30-90 segundos', b.motivo_entrada(gang, True, 'impulse'))

    def test_session_fifteen_reads_cover_fourteen_minutes(self):
        elapsed = [0.0]
        read_times = []
        def read(**kwargs):
            read_times.append(elapsed[0])
            elapsed[0] += 3
        def sleep(delay):
            elapsed[0] += delay
        with patch.object(b.time, 'monotonic', side_effect=lambda: elapsed[0]), \
             patch.object(b.time, 'sleep', side_effect=sleep), patch.object(b, 'main', side_effect=read):
            b.run_session(15)
        self.assertEqual(read_times, list(range(0, 841, 60)))
        self.assertLess(elapsed[0], 900)
        elapsed[0] = 0
        def slow_read(**kwargs):
            elapsed[0] += 901
        with patch.object(b.time, 'monotonic', side_effect=lambda: elapsed[0]), \
             patch.object(b.time, 'sleep') as sleep_mock, patch.object(b, 'main', side_effect=slow_read) as main:
            b.run_session(15)
        self.assertEqual(main.call_count, 1)
        sleep_mock.assert_not_called()

    def test_candidate_outside_top10_can_confirm_and_enter_both_wallets(self):
        ranking = [b.analizar_par(pair(address=f'a{i}', pool=f'p{i}', price=.95))
                   for i in range(12)]
        with patch.object(b, 'datetime') as clock:
            clock.now.return_value = datetime.now(timezone.utc)-timedelta(minutes=1)
            b.guardar_memoria(ranking)
        previous = b.cargar_memoria()
        self.assertEqual(len(previous), 12)
        self.assertEqual(previous[-1]['address'], 'a11')
        fresh_pair = pair(address='a11', pool='p11', price=1)
        fresh_pair['volume']['m5'] = 4500
        fresh = b.analizar_par(fresh_pair)
        with patch.object(b, 'cotizar_posicion', return_value=(1, 20000, fresh_pair)):
            for mode, filename in [('early', b.V10_FILE), ('impulse', b.V10_IMPULSE_FILE)]:
                b.simular_cartera([fresh], filename, mode, True, mode)
                with open(filename) as handle:
                    state = json.load(handle)
                self.assertEqual(state['cash'], 90)
                self.assertEqual(state['positions'][0]['address'], 'a11')
                self.assertEqual(state['positions'][0]['entry_confirmation']['pair'], 'p11')
                self.assertIn('todos los candidatos', state['assumptions']['candidate_memory_scope'])

    def test_full_candidate_memory_keeps_history_bounded(self):
        with open(b.MEMORY_FILE, 'w') as handle:
            json.dump([{'marker': i} for i in range(10000)], handle)
        ranking = [b.analizar_par(pair(address=f'a{i}', pool=f'p{i}')) for i in range(12)]
        b.guardar_memoria(ranking)
        memory = b.cargar_memoria()
        self.assertEqual(len(memory), 10000)
        self.assertEqual(memory[0]['marker'], 12)
        self.assertEqual([x['address'] for x in memory[-12:]], [f'a{i}' for i in range(12)])

    def test_v9_fomo_confluence_is_bounded_and_verified(self):
        t = b.analizar_par(pair())
        candidates = {("solana", "a"): t}
        events = [
            {"chain": "solana", "address": "a", "trader": "T1", "side": "BUY", "verified": True},
            {"chain": "solana", "address": "a", "trader": "T2", "side": "BUY", "verified": True},
            {"chain": "solana", "address": "a", "trader": "T3", "side": "SELL", "verified": True},
        ]
        base = t["score"]
        b.aplicar_confluencia_fomo(candidates, events)
        self.assertEqual(t["fomoConfluence"], 2)
        self.assertEqual(t["fomoBonus"], 1)
        self.assertEqual(t["score"], base + 1)

    def test_v9_no_feed_means_no_fabricated_events(self):
        with patch.object(b, "FOMO_RADAR_CONNECTED", False):
            self.assertEqual(b.consultar_fomo_trader_radar(), [])
            self.assertEqual(b.FOMO_RADAR_STATUS, "SIN FUENTE AUTORIZADA")

    def test_nonfinite_prices_rejected(self):
        self.assertEqual(b.numero('NaN'), 0)
        self.assertEqual(b.numero('Infinity'), 0)
        with self.assertRaises(ValueError):
            self.quote([pair(pool='old', price='NaN')], [])


if __name__ == '__main__':
    with contextlib.redirect_stdout(io.StringIO()):
        unittest.main()

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
        t.update(trades5m=20, buyRatio5m=.55, ageMinutes=30,
                 liquidity=20000, vol5m=3000)
        old = dict(t, hora=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                   price=.95, liquidity=21000, vol5m=5000)
        with patch.object(b, 'cargar_memoria', return_value=[old]):
            self.assertIsNone(b.motivo_entrada(t, True))
            for field, value in [('trades5m', 19), ('buyRatio5m', .54),
                                 ('ageMinutes', 61), ('change5m', 61),
                                 ('liquidity', 19000), ('vol5m', 2999),
                                 ('price', .94)]:
                with self.subTest(field=field):
                    rejected = dict(t, **{field: value})
                    self.assertIsNotNone(b.motivo_entrada(rejected, True))

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

    def test_session_clears_cache_between_reads(self):
        b.JSON_CACHE['stale'] = {}
        with patch.object(b, 'main') as main, patch.object(b.time, 'sleep'), patch.object(b.time, 'monotonic', return_value=0):
            b.run_session(2)
            self.assertEqual(main.call_count, 2)
        self.assertEqual(b.JSON_CACHE, {})
        with self.assertRaises(ValueError):
            b.run_session(14)

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

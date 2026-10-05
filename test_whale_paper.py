import unittest
import tempfile
import json
from unittest.mock import patch
import whale_paper as w


def alert(**overrides):
    return dict({'type': 'alert', 'source': 'feed', 'trader': w.TRADER,
                 'alertType': 'buy', 'ts': 1060000, 'chainId': 4663,
                 'tokenAddress': '0xabc', 'eventId': 'e1', 'userId': 'u1', 'token': 'TEST'}, **overrides)


def state():
    return {'cash': 100., 'realized': 0., 'positions': [], 'closed': [], 'events': [], 'seen': []}


class WhaleTests(unittest.TestCase):
    def test_forward_only_not_gifts_or_other_traders(self):
        self.assertIsNotNone(w.normalize(alert(), 1120, 1000)[0])
        for changes in ({'ts': 999000}, {'ts': 900000}, {'ts': 1121000},
                        {'alertType': 'transfer'}, {'trader': 'other'}, {'eventId': None},
                        {'chainId': 999}, {'ts': float('nan')}):
            self.assertIsNone(w.normalize(alert(**changes), 1120, 1000)[0])

    def test_dedup_and_costs_are_ours(self):
        s = state()
        e, _ = w.normalize(alert(), 1120, 1000)
        w.process(s, e, 1120, lambda _: (1., 'pool'))
        w.process(s, e, 1121, lambda _: self.fail('duplicate quoted'))
        self.assertEqual(len(s['positions']), 1)
        self.assertEqual(s['cash'], 90)
        sell, _ = w.normalize(alert(alertType='sell', eventId='e2'), 1120, 1000)
        w.process(s, sell, 1120, lambda _: (1., 'pool'))
        self.assertAlmostEqual(s['realized'], 10*(.99*.98)/(1.01*1.02)-10)
        self.assertAlmostEqual(s['cash'], 100+s['realized'])
        self.assertFalse(e['transaction_verified'])

    def test_unpriced_keeps_position_and_blocks_buys(self):
        s = state()
        e, _ = w.normalize(alert(), 1120, 1000)
        w.process(s, e, 1120, lambda _: (1., 'pool'))
        def unavailable(_):
            raise ValueError('unavailable')
        w.mark(s, 1180, unavailable)
        self.assertFalse(s['equity_verified'])
        self.assertEqual(len(s['positions']), 1)
        other, _ = w.normalize(alert(eventId='e2', tokenAddress='0xdef'), 1120, 1000)
        w.process(s, other, 1120, lambda _: self.fail('paused buy quoted'))
        self.assertIn('DESCARTE', other['result'])
        self.assertEqual(s['cash'], 90)

    def test_user_id_change_is_rejected(self):
        s = state()
        s['user_id'] = 'original'
        e, _ = w.normalize(alert(), 1120, 1000)
        w.process(s, e, 1120, lambda _: self.fail('identity change quoted'))
        self.assertEqual(s['cash'], 100)

    def test_state_cannot_cross_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = directory + '/state.json'
            with open(path, 'w') as f:
                json.dump({'trader': 'FartmanSacks'}, f)
            with patch.object(w, 'FILE', path), patch.object(w, 'TRADER', 'unipcs'):
                with self.assertRaises(ValueError):
                    w.load()

    def test_selected_trader_rejects_other_profile(self):
        with patch.object(w, 'TRADER', 'unipcs'):
            self.assertIsNone(w.normalize(alert(trader='FartmanSacks'), 1120, 1000)[0])
            self.assertIsNotNone(w.normalize(alert(trader='unipcs'), 1120, 1000)[0])

    def test_gecko_rate_budget_does_not_send_extra_request(self):
        import time
        with patch.object(w, 'GECKO_CALLS', [time.monotonic()] * 10), patch.object(w.brain, 'pedir_json') as fetch:
            with self.assertRaises(ValueError):
                w.gecko_json('https://example.test')
            fetch.assert_not_called()

    def test_gecko_exact_identity_and_quote_side(self):
        def pool(address, base, quote, price, reserve=20000):
            return {'id': 'robinhood_' + address,
                    'attributes': {'address': address, 'base_token_price_usd': '3000',
                                   'quote_token_price_usd': price, 'reserve_in_usd': reserve},
                    'relationships': {'base_token': {'data': {'id': 'robinhood_' + base}},
                                      'quote_token': {'data': {'id': 'robinhood_' + quote}}}}
        good = pool('pool', 'weth', '0xabc', '0.02')
        wrong = pool('wrong', 'weth', 'other', '200', 9999999)
        price, pool_id, reserve = w.gecko_pool({'data': [wrong, good]}, '0xABC')
        self.assertEqual(price, .02)
        self.assertEqual(pool_id, 'pool')
        for row in [wrong, pool('p', 'weth', '0xabc', '.02', 9999),
                    pool('p', 'weth', '0xabc', 'nan')]:
            with self.assertRaises(ValueError):
                w.gecko_pool({'data': [row]}, '0xabc')

    def test_robinhood_fallback_wires_provider_and_identity(self):
        payload = {'data': [{'id': 'robinhood_pool', 'attributes': {
            'address': 'pool', 'base_token_price_usd': '.03', 'reserve_in_usd': '20000'},
            'relationships': {'base_token': {'data': {'id': 'robinhood_0xabc'}}}}]}
        e, _ = w.normalize(alert(), 1120, 1000)
        with patch.object(w.brain, 'pares_token', return_value=[]), patch.object(w.brain, 'pedir_json', return_value=payload) as fetch:
            self.assertEqual(w.quote(e), (.03, 'pool'))
            self.assertEqual(e['quote_source'], 'geckoterminal')
            self.assertIn('/tokens/0xabc/pools', fetch.call_args.args[0])
        with patch.object(w.brain, 'pares_token', return_value=[]), patch.object(w.brain, 'pedir_json') as fetch:
            with self.assertRaises(ValueError):
                w.quote(dict(e, chain='solana'))
            fetch.assert_not_called()

    def test_candles_drop_unfinished_and_invalid_bars(self):
        payload = {'data': {'attributes': {'ohlcv_list': [
            [960, 1, 2, .9, 1.2, 100], [1080, 1, 2, .9, 1.2, 200],
            [900, 1, .5, .9, 1.2, 100], [0, 1, 2, .9, 1.2, 100]]}}}
        result = w.candle_context(payload, 1120)
        self.assertEqual(len(result['bars']), 1)
        self.assertAlmostEqual(result['body_pct'], 20)

    def test_positive_profit_reserve_and_equity(self):
        s = state()
        e, _ = w.normalize(alert(), 1120, 1000)
        w.process(s, e, 1120, lambda _: (1., 'pool'))
        sell, _ = w.normalize(alert(alertType='sell', eventId='sell'), 1120, 1000)
        w.process(s, sell, 1120, lambda _: (2., 'pool'))
        profit = 20*w.SELL_FACTOR/w.BUY_FACTOR - 10
        self.assertAlmostEqual(s['reserve'], profit/2)
        self.assertAlmostEqual(s['cash'], 100 + profit/2)
        w.mark(s, 1120)
        self.assertAlmostEqual(s['last_accounting_equity'], 100 + profit)

    def test_quote_failure_records_reason_without_spending(self):
        s = state()
        e, _ = w.normalize(alert(), 1120, 1000)
        def unavailable(_):
            raise ValueError('GeckoTerminal: sin pool exacto')
        w.process(s, e, 1120, unavailable)
        self.assertIn('sin pool exacto', e['quote_error'])
        self.assertEqual(s['cash'], 100)
        self.assertFalse(s['positions'])

    def test_peer_buy_is_observed_correlation_and_needs_same_contract(self):
        peer = {'trader': 'unipcs', 'user_id': 'peer', 'events': [
            {'side': 'buy', 'chain': 'robinhood', 'address': '0xABC', 'source_at': w.stamp(1060)}]}
        e, _ = w.normalize(alert(), 1120, 1000)
        from unittest.mock import mock_open
        with patch('builtins.open', mock_open(read_data=json.dumps(peer))):
            self.assertEqual(w.peer_buys(e, 1120), ['unipcs'])
            self.assertEqual(w.peer_buys(dict(e, address='other'), 1120), [])
            self.assertEqual(w.peer_buys(e, 1300), [])

    def test_stop_uses_current_quote_net_costs(self):
        s = state()
        e, _ = w.normalize(alert(), 1120, 1000)
        w.process(s, e, 1120, lambda _: (1., 'pool'))
        w.mark(s, 1180, lambda _: (.85, 'pool'))
        self.assertEqual(len(s['positions']), 0)
        self.assertAlmostEqual(s['realized'], 10*.85*(.99*.98)/(1.01*1.02)-10)


if __name__ == '__main__':
    unittest.main()


import unittest
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
        self.assertAlmostEqual(s['realized'], 10*.97/1.03-10)
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

    def test_stop_uses_current_quote_net_costs(self):
        s = state()
        e, _ = w.normalize(alert(), 1120, 1000)
        w.process(s, e, 1120, lambda _: (1., 'pool'))
        w.mark(s, 1180, lambda _: (.85, 'pool'))
        self.assertEqual(len(s['positions']), 0)
        self.assertAlmostEqual(s['realized'], 10*.85*.97/1.03-10)


if __name__ == '__main__':
    unittest.main()

import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import fomo_brain as brain
import targets_lab as lab
from m4_lab import write


class TargetsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def read(self, path=lab.STAGED):
        with open(path) as h:
            return json.load(h)

    def test_start_once_and_missing_state_never_resets(self):
        self.assertTrue(lab.bootstrap())
        a, b = self.read(lab.CONTROL), self.read()
        self.assertEqual(a['targets_baseline'], b['targets_baseline'])
        self.assertEqual(a['cash'], b['cash'])
        b['cash'] = 91
        write(lab.STAGED, b)
        self.assertFalse(lab.bootstrap())
        self.assertEqual(self.read()['cash'], 91)
        os.remove(lab.CONTROL)
        with self.assertRaises(ValueError):
            lab.bootstrap()

    def seed_position(self):
        lab.bootstrap()
        state = self.read()
        state['cash'] = 95
        state['positions'] = [dict(symbol='TEST', address='test', chain='solana',
            pair='pool', quantity=5., budget=5., mark_net=5., entry_price=1.,
            opened_at=datetime.now(timezone.utc).isoformat(), quote_status='OK',
            last_quote_at=datetime.now(timezone.utc).isoformat(),
            partial_taken=False, peak_price=1.)]
        write(lab.STAGED, state)

    def tick(self, pnl=None):
        factor = (1-brain.PAPER_FEE)*(1-brain.PAPER_SLIPPAGE)
        quote = patch.object(brain, 'cotizar_posicion', side_effect=ValueError('unavailable')) if pnl is None else patch.object(brain, 'cotizar_posicion', return_value=((1+pnl/100)/factor, 25000, {}))
        with quote, contextlib.redirect_stdout(io.StringIO()):
            brain.simular_cartera([], lab.STAGED, staged_targets=True)
        return self.read()

    def test_three_targets_conserve_cost_quantity_cash_and_reserve(self):
        self.seed_position()
        a = self.tick(16)
        self.assertAlmostEqual(a['positions'][0]['quantity'], 2.5)
        self.assertEqual(a['positions'][0]['targets_stage'], 1)
        b = self.tick(31)
        self.assertAlmostEqual(b['positions'][0]['quantity'], 1.25)
        c = self.tick(46)
        self.assertFalse(c['positions'])
        self.assertAlmostEqual(sum(x['allocated_cost'] for x in c['closed']), 5.)
        self.assertAlmostEqual(sum(x['sold_quantity'] for x in c['closed']), 5.)
        profit = sum(x['profit'] for x in c['closed'])
        self.assertAlmostEqual(c['cash']+c['reserve'], 100+profit)
        self.assertAlmostEqual(c['reserve'], profit/2)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(lab.report()['staged']['completed_positions'], 1)

    def test_gap_fills_only_observed_price_and_protection_can_overshoot(self):
        self.seed_position()
        a = self.tick(35)
        self.assertEqual(len(a['closed']), 1)
        self.assertAlmostEqual(a['closed'][0]['sold_quantity'], 3.75)
        b = self.tick(-4)
        self.assertFalse(b['positions'])
        self.assertEqual(b['closed'][-1]['exit_reason'], 'TARGETS PROTECCION +2%')
        self.assertLess(b['closed'][-1]['profit'], 0)

    def test_unknown_never_sells_or_becomes_liquidity(self):
        self.seed_position()
        a = self.tick()
        self.assertEqual(a['cash'], 95)
        self.assertFalse(a['closed'])
        self.assertIsNone(a['observations'][-1]['estimated_equity'])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(lab.report()['advantage'])

    def test_policy_isolated_and_uninitialized_rejected(self):
        for path, enabled in ((brain.V10_FILE, True), (lab.STAGED, True), (lab.CONTROL, False)):
            with self.assertRaises(ValueError):
                brain.simular_cartera([], path, staged_targets=enabled)
        self.assertFalse(os.path.exists(lab.STAGED))

    def test_runner_uses_same_candidates_and_guard_and_watchdog_policy(self):
        from unittest.mock import Mock
        lab.bootstrap()
        sim = Mock()
        with patch('candle_lab.guard', return_value=None), contextlib.redirect_stdout(io.StringIO()):
            lab.run([{'address': 'same'}], sim)
        self.assertEqual(sim.call_args_list[0].args[0], sim.call_args_list[1].args[0])
        self.assertFalse(sim.call_args_list[0].kwargs['staged_targets'])
        self.assertTrue(sim.call_args_list[1].kwargs['staged_targets'])
        self.seed_position()
        with patch.dict(os.environ, {'BRAIN_TARGETS_LAB': '1'}), patch.object(brain, 'simular_cartera') as run, contextlib.redirect_stdout(io.StringIO()):
            brain.refresh_open_positions()
        call = next(c for c in run.call_args_list if c.args[1] == lab.STAGED)
        self.assertEqual(call.args[0], [])
        self.assertTrue(call.kwargs['staged_targets'])


if __name__ == '__main__':
    unittest.main()

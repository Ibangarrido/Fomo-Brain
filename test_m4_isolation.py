import copy
import contextlib
import io
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import test_m4_lab
import m4_lab as lab
import fomo_brain as brain


class IsolationTests(unittest.TestCase):
    def setUp(self):
        test_m4_lab.M4Tests.setUp(self)
        self.seed['positions'][0]['quantity'] = lab.INHERITED_QUANTITY
        self.env = patch.dict(os.environ, BRAIN_M4_ISOLATION='1')
        self.env.start()

    def tearDown(self):
        self.env.stop()
        test_m4_lab.M4Tests.tearDown(self)

    read = test_m4_lab.M4Tests.read

    def test_migration_preserves_accounting_and_records_one_epoch(self):
        before = copy.deepcopy(self.seed)
        for _ in range(2):
            self.assertTrue(lab.isolate_inherited(self.seed, lab.SOURCE, datetime.now(timezone.utc)))
        for key in ('cash', 'reserve', 'closed', 'seen'):
            self.assertEqual(self.seed[key], before[key])
        for key in ('quantity', 'budget', 'mark_net', 'opened_at'):
            self.assertEqual(self.seed['positions'][0][key], before['positions'][0][key])
        self.assertEqual(len(self.seed['m4_isolation_history']), 1)

    def test_only_exact_legacy_position_is_eligible(self):
        for changes in ({'chain':'other'}, {'address':'other'}, {'quantity':100},
                        {'budget':6}, {'opened_at':'2026-10-07T23:11:00+00:00'},
                        {'quote_status':'OK'}):
            state = copy.deepcopy(self.seed)
            state['positions'][0].update(changes)
            self.assertFalse(lab.isolate_inherited(state, lab.SOURCE, datetime.now(timezone.utc)))
        self.assertFalse(lab.isolate_inherited(self.seed, lab.CONTROL, datetime.now(timezone.utc)))
        state = copy.deepcopy(self.seed)
        state['positions'].append(copy.deepcopy(state['positions'][0]))
        self.assertFalse(lab.isolate_inherited(state, lab.SOURCE, datetime.now(timezone.utc)))

    def run_isolated(self, state):
        lab.write(lab.SOURCE, state)
        with patch.object(brain, 'cotizar_posicion', side_effect=ValueError('No quote')), contextlib.redirect_stdout(io.StringIO()):
            brain.simular_cartera([], lab.SOURCE)
        return self.read(lab.SOURCE)

    def test_unknown_m4_does_not_pause_or_create_a_sale(self):
        state = self.run_isolated(self.seed)
        self.assertFalse(any('ENTRADAS PAUSADAS' in n for n in state['last_run_notes']))
        self.assertEqual((state['cash'],state['reserve'],state['closed']), (82,10,[]))
        self.assertEqual(state['positions'][0]['quantity'], lab.INHERITED_QUANTITY)
        self.assertIsNone(state['observations'][-1]['estimated_equity'])

    def test_other_unknown_position_still_pauses(self):
        state = copy.deepcopy(self.seed)
        state['positions'].append(dict(state['positions'][0], address='other'))
        state = self.run_isolated(state)
        self.assertTrue(any('ENTRADAS PAUSADAS' in n for n in state['last_run_notes']))

    def test_capital_loss_and_existing_halt_still_apply(self):
        state = copy.deepcopy(self.seed)
        state['cash'] = 60
        state = self.run_isolated(state)
        self.assertTrue(any('FRENO V10' in n for n in state['last_run_notes']))
        self.assertEqual(state['cash'], 60)
        self.assertEqual(state['closed'], [])

    def test_cash_only_epoch_preserves_unknown_and_blocks_later_unknowns(self):
        path = 'fomo_paper_v10.json'
        def run(state):
            lab.write(path, state)
            with patch.dict(os.environ, BRAIN_UNKNOWN_ISOLATION='1'), patch.object(brain, 'cotizar_posicion', side_effect=ValueError('No quote')), contextlib.redirect_stdout(io.StringIO()):
                brain.simular_cartera([], path)
            return self.read(path)
        state = run(copy.deepcopy(self.seed))
        self.assertFalse(any('ENTRADAS PAUSADAS' in n for n in state['last_run_notes']))
        self.assertEqual((state['cash'], state['reserve'], state['closed']), (82, 10, []))
        self.assertEqual(state['positions'][0]['quantity'], lab.INHERITED_QUANTITY)
        self.assertIsNone(state['observations'][-1]['estimated_equity'])
        epoch = copy.deepcopy(state['unknown_isolation_epoch'])
        state['positions'].append(dict(state['positions'][0], address='new_unknown'))
        state = run(state)
        self.assertEqual(state['unknown_isolation_epoch'], epoch)
        self.assertTrue(any('ENTRADAS PAUSADAS' in n for n in state['last_run_notes']))
        state['cash'] = 60
        state['reserve'] = 0
        state = run(state)
        self.assertTrue(any('FRENO V10' in n for n in state['last_run_notes']))


if __name__ == '__main__':
    unittest.main()


import copy
import contextlib
import io
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import test_m4_lab
from test_fomo_v8 import pair
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

    def test_legacy_unknowns_are_excluded_from_entry_slot_preflight(self):
        state = copy.deepcopy(self.seed)
        for i in range(2):
            state["positions"].append(dict(state["positions"][0], address=f"legacy_{i}"))
        state["cash"] = 82
        path = "fomo_paper_v10.json"
        lab.write(path, state)
        candidate = brain.analizar_par(pair(address="candidate", pool="pool"))
        with patch.dict(os.environ, BRAIN_UNKNOWN_ISOLATION="1"), \
             patch.object(brain, "cotizar_posicion", side_effect=ValueError("No quote")), \
             contextlib.redirect_stdout(io.StringIO()):
            brain.simular_cartera([candidate], path)
        updated = self.read(path)
        self.assertEqual(len(updated["positions"]), 3)
        self.assertEqual(updated["cash"], 82)
        self.assertEqual(updated["closed"], [])
        self.assertEqual(updated["last_m4_shadow_preflight"]["unknown_valuation_only_at_preflight"], 0)
        # The quote is deliberately unavailable: prove that the isolated
        # historical slots did not stop the candidate before quote preflight.
        self.assertFalse(any("maximo 3 posiciones" in note for note in updated["last_run_notes"]))
        self.assertTrue(any("ENTRADA OMITIDA solana:candidate" in note for note in updated["last_run_notes"]))

    def test_continuation_control_unknown_epoch_reaches_quote_preflight(self):
        # Exact experimental wallet affected in production: preserve inherited
        # accounting, exclude its old unknown mark, and still require a quote.
        state = copy.deepcopy(self.seed)
        state['continuation_experiment'] = {'version': 'continuation-r1', 'arm': 'control'}
        path = 'fomo_lab_continuation_control_r1.json'
        lab.write(path, state)
        candidate = brain.analizar_par(pair(address='candidate_control', pool='pool'))
        self.assertIsNotNone(candidate)
        with patch.dict(os.environ, BRAIN_UNKNOWN_ISOLATION='1'), \
             patch.object(brain, 'cotizar_posicion', side_effect=ValueError('No quote')), \
             contextlib.redirect_stdout(io.StringIO()):
            brain.simular_cartera([candidate], path, entry_mode='early', min_buy_ratio=.75)
        updated = self.read(path)
        self.assertEqual((updated['cash'], updated['reserve'], updated['closed']), (82, 10, []))
        self.assertEqual(len(updated['positions']), 1)
        self.assertIsNone(updated['observations'][-1]['estimated_equity'])
        self.assertEqual(updated['last_m4_shadow_preflight']['unknown_valuation_only_at_preflight'], 0)
        self.assertFalse(any('cartera sin valoracion completa' in n or 'maximo 3 posiciones' in n
                             for n in updated['last_run_notes']))
        self.assertTrue(any('ENTRADA OMITIDA solana:candidate_control' in n
                            for n in updated['last_run_notes']))

    def test_real_continuation_coin_is_not_legacy_m4_and_requires_opt_in(self):
        # The observed CONTINUATION CONTROL unknown is Coin, not the M4 mint.
        # Compare the unchanged policy with an explicitly enabled PAPER epoch.
        path = 'fomo_lab_continuation_control_r1.json'
        state = copy.deepcopy(self.seed)
        state['positions'][0]['address'] = 'CJYxdC79qMe94db5cS6wMh7oi5Fsy3BJQMH2KxVB3my3'
        state['continuation_experiment'] = {'version': 'continuation-r1', 'arm': 'control'}
        self.assertNotEqual(state['positions'][0]['address'], lab.MINT)
        candidate = brain.analizar_par(pair(address='coin_epoch_candidate', pool='pool'))
        self.assertIsNotNone(candidate)
        for enabled in ('0', '1'):
            with self.subTest(unknown_isolation=enabled):
                lab.write(path, copy.deepcopy(state))
                with patch.dict(os.environ, BRAIN_UNKNOWN_ISOLATION=enabled), \
                     patch.object(brain, 'cotizar_posicion', side_effect=ValueError('No quote')), \
                     contextlib.redirect_stdout(io.StringIO()):
                    brain.simular_cartera([candidate], path, entry_mode='early', min_buy_ratio=.75)
                updated = self.read(path)
                self.assertEqual((updated['cash'], updated['reserve'], updated['closed']),
                                 (82, 10, []))
                self.assertEqual(len(updated['positions']), 1)
                self.assertEqual(updated['positions'][0]['address'],
                                 state['positions'][0]['address'])
                self.assertIsNone(updated['observations'][-1]['estimated_equity'])
                notes = updated['last_run_notes']
                if enabled == '0':
                    self.assertTrue(any('cartera sin valoracion completa' in n for n in notes))
                    self.assertNotIn('unknown_isolation_epoch', updated)
                else:
                    self.assertFalse(any('cartera sin valoracion completa' in n for n in notes))
                    self.assertTrue(any('ENTRADA OMITIDA solana:coin_epoch_candidate' in n
                                        for n in notes))
                    self.assertEqual(len(updated['unknown_isolation_epoch']['positions']), 1)

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


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


    def test_control_workflow_pins_exact_legacy_contract(self):
        from pathlib import Path
        workflow = Path(__file__).resolve().parent / ".github/workflows/fomo_brain.yml"
        source = workflow.read_text(encoding="utf-8")
        self.assertIn('BRAIN_UNKNOWN_ISOLATION: "1"', source)
        self.assertIn(
            'BRAIN_CONTROL_LEGACY_ADDRESS: "CJYxdC79qMe94db5cS6wMh7oi5Fsy3BJQMH2KxVB3my3"',
            source,
        )

    def test_control_requires_pinned_legacy_and_preserves_cash(self):
        path = "fomo_lab_continuation_control_r1.json"
        state = copy.deepcopy(self.seed)
        coin_mint = "CJYxdC79qMe94db5cS6wMh7oi5Fsy3BJQMH2KxVB3my3"
        state["positions"][0]["address"] = coin_mint
        state["positions"][0]["symbol"] = "Coin"
        original = copy.deepcopy(state)
        now = datetime.now(timezone.utc)
        with patch.dict(os.environ, {"BRAIN_UNKNOWN_ISOLATION": "1"}, clear=False):
            self.assertEqual(brain.isolate_existing_unknowns(state, path, now), set())
            self.assertNotIn("unknown_isolation_epoch", state)
            with patch.dict(os.environ, {"BRAIN_CONTROL_LEGACY_ADDRESS": "wrong"}):
                self.assertEqual(brain.isolate_existing_unknowns(state, path, now), set())
            with patch.dict(os.environ, {"BRAIN_CONTROL_LEGACY_ADDRESS": coin_mint}):
                keys = brain.isolate_existing_unknowns(state, path, now)
                self.assertEqual(len(keys), 1)
                with patch.dict(os.environ, {"BRAIN_CONTROL_LEGACY_ADDRESS": "wrong"}):
                    self.assertEqual(brain.isolate_existing_unknowns(state, path, now), set())
                self.assertEqual((state["cash"], state["reserve"], state["closed"]),
                                 (original["cash"], original["reserve"], original["closed"]))
                state["positions"].append(dict(state["positions"][0], address="new_unknown"))
                self.assertEqual(brain.isolate_existing_unknowns(state, path, now), keys)
                self.assertNotIn(("solana", "new_unknown", state["positions"][-1]["opened_at"]), keys)


    def test_control_real_coin_cash_preserved_and_new_unknown_still_blocks(self):
        path = "fomo_lab_continuation_control_r1.json"
        coin = "CJYxdC79qMe94db5cS6wMh7oi5Fsy3BJQMH2KxVB3my3"
        state = copy.deepcopy(self.seed)
        state["positions"][0].update(address=coin, symbol="Coin")
        state["continuation_experiment"] = {"version": "continuation-r1", "arm": "control"}
        state["cash"], state["reserve"] = 98.58, 1.08
        before = copy.deepcopy(state)
        def run(snapshot, pin):
            lab.write(path, snapshot)
            with (
                patch.dict(os.environ, {"BRAIN_UNKNOWN_ISOLATION": "1",
                                       "BRAIN_CONTROL_LEGACY_ADDRESS": pin}),
                patch.object(brain, "cotizar_posicion",
                             side_effect=ValueError("No verified quote")),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                brain.simular_cartera([], path, label="LAB CONTINUATION control",
                                      entry_mode="early", min_buy_ratio=.75)
            return self.read(path)
        # No pin means the historical unknown remains an active safety blocker.
        unpinned = run(copy.deepcopy(before), "")
        self.assertTrue(any("ENTRADAS PAUSADAS" in n
                            for n in unpinned["last_run_notes"]))
        self.assertNotIn("unknown_isolation_epoch", unpinned)
        # Exact pin permits a PAPER-only policy epoch; it is not a sale.
        isolated = run(copy.deepcopy(before), coin)
        self.assertFalse(any("ENTRADAS PAUSADAS" in n
                             for n in isolated["last_run_notes"]))
        self.assertEqual((isolated["cash"], isolated["reserve"], isolated["closed"]),
                         (before["cash"], before["reserve"], before["closed"]))
        self.assertEqual(isolated["positions"][0]["quantity"],
                         before["positions"][0]["quantity"])
        self.assertIsNone(isolated["observations"][-1]["estimated_equity"])
        self.assertEqual(len(isolated["unknown_isolation_epoch"]["positions"]), 1)
        # A second, later unknown must never be silently isolated.
        isolated["positions"].append(dict(isolated["positions"][0],
                                          address="unverified_new_token"))
        blocked = run(isolated, coin)
        self.assertTrue(any("ENTRADAS PAUSADAS" in n
                            for n in blocked["last_run_notes"]))
        self.assertEqual((blocked["cash"], blocked["reserve"], blocked["closed"]),
                         (before["cash"], before["reserve"], before["closed"]))


if __name__ == '__main__':
    unittest.main()


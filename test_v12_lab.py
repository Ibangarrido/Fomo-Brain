import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import v12_lab as v
import fomo_brain as brain
from test_fomo_v8 import pair


class V12Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.temp.name)
        self.t = datetime(2026, 10, 18, tzinfo=timezone.utc)
        self.token = dict(chain='solana', address='Mint', pair='Pool', price=1,
                          received_at=self.t.isoformat(), symbol='TEST')
        self.state = v.read()
        self.notes = ['DESCARTE solana:Mint | score < 5']

    def tearDown(self):
        os.chdir(self.old)
        self.temp.cleanup()

    def register(self, arm='V11 CONTROL 100 EUR', at=None):
        v.register_rejections(self.state, arm, [self.token], self.notes, at or self.t)

    def quote(self, at, price=1.1, **kwargs):
        return dict(self.token, received_at=at.isoformat(), price=price, **kwargs)

    def test_prospective_dedup_and_independent_reasons(self):
        self.register(); self.register(at=self.t+timedelta(seconds=60))
        self.register('V11 NET 100 EUR')
        self.assertEqual(len(self.state['cases']), 2)
        self.assertEqual(self.state['evaluations']['CONTROL']['rejected'], 2)
        self.assertEqual(self.state['cases'][0]['reason'], 'score < 5')

    def test_restart_and_forward_5m_then_15m(self):
        self.register(); v.save(self.state)
        resumed = v.read()
        t5 = self.t+timedelta(minutes=5)
        calls = []
        v.refresh(resumed, lambda token: calls.append(token) or self.quote(t5), t5)
        self.assertEqual(len(calls), 1)
        self.assertEqual(resumed['cases'][0]['horizons']['5']['return_pct'], 10)
        t15 = self.t+timedelta(minutes=15)
        v.refresh(resumed, lambda _: self.quote(t15, .9), t15)
        self.assertEqual(resumed['cases'][0]['horizons']['15']['return_pct'], -10)
        self.assertNotIn('30', resumed['cases'][0]['horizons'])

    def test_gaps_never_fill_old_horizons_with_later_quotes(self):
        self.register()
        t = self.t+timedelta(minutes=31)
        v.refresh(self.state, lambda _: self.quote(t, 2), t)
        h = self.state['cases'][0]['horizons']
        self.assertIsNone(h['5']['return_pct']); self.assertIsNone(h['15']['return_pct'])
        self.assertEqual(h['30']['return_pct'], 100)

    def test_missing_wrong_contract_pair_stale_nan_and_future_quotes_stay_unknown(self):
        for change in ({'address':'Other'}, {'pair':'Other'}, {'chain':'base'}, {'price':float('nan')},
                       {'received_at':(self.t+timedelta(minutes=4)).isoformat()},
                       {'received_at':(self.t+timedelta(minutes=6)).isoformat()}):
            with self.subTest(change=change):
                self.state=v.read(); self.register()
                t=self.t+timedelta(minutes=5)
                sample=self.quote(t); sample.update(change)
                v.refresh(self.state, lambda _: sample, t)
                self.assertEqual(self.state['cases'][0]['horizons'], {})
                v.refresh(self.state, lambda _: sample, t+timedelta(seconds=121))
                self.assertEqual(self.state['cases'][0]['horizons']['5']['status'], 'unknown')

    def test_network_failure_then_later_valid_quote_recovers(self):
        self.register(); t=self.t+timedelta(minutes=5)
        def fail(_): raise OSError('no provider')
        v.refresh(self.state, fail, t)
        self.assertIn('no provider', self.state['cases'][0]['last_quote_error'])
        later=t+timedelta(seconds=30)
        v.refresh(self.state, lambda _: self.quote(later), later)
        self.assertEqual(self.state['cases'][0]['horizons']['5']['status'], 'observed')

    def test_receipt_after_slow_request_uses_completion_clock(self):
        self.register(); t=self.t+timedelta(minutes=5); end=t+timedelta(seconds=2)
        v.refresh(self.state, lambda _: self.quote(end), t, clock=lambda:end)
        self.assertEqual(self.state['cases'][0]['horizons']['5']['status'],'observed')

    def test_quote_requests_deduplicate_arms_and_are_bounded(self):
        for i in range(25):
            self.token.update(address=str(i), pair=str(i))
            self.notes=['DESCARTE solana:'+str(i)+' | score < 5']
            self.register(); self.register('V11 NET 100 EUR')
        t=self.t+timedelta(minutes=5); calls=[]
        v.refresh(self.state, lambda token: calls.append(token) or dict(token,price=1.1,received_at=t.isoformat()), t)
        self.assertEqual(len(calls),v.MAX_QUOTES)
        self.assertEqual(sum('5' in c['horizons'] for c in self.state['cases']),40)

    def test_invalid_reference_and_corrupt_file_never_reset(self):
        self.token['received_at']=(self.t-timedelta(minutes=2)).isoformat(); self.register()
        self.assertEqual(self.state['invalid_references'],1); self.assertEqual(self.state['cases'],[])
        open(v.FILE,'w').write('{broken')
        with self.assertRaises(ValueError): v.read()
        self.assertEqual(open(v.FILE).read(),'{broken')

    def test_partial_legs_reconcile_without_double_counting(self):
        budget=5; qty=budget/(1.01*1.02); exit_price=1.2
        def leg(fraction):
            sold=qty*fraction; allocated=budget*fraction; proceeds=sold*exit_price*.99*.98
            return dict(sold_quantity=sold,entry_price=1,exit_price=exit_price,
                        allocated_cost=allocated,proceeds=proceeds,profit=proceeds-allocated)
        wallet={'cash':100,'reserve':0,'positions':[],'closed':[leg(.5),leg(.5)]}
        before=copy.deepcopy(wallet); r=v.wallet_outcomes(wallet)
        self.assertEqual(wallet,before)
        expected=qty*exit_price*.99*.98-budget
        self.assertAlmostEqual(r['modeled_realized_net_pnl_eur'],expected,places=7)
        self.assertIsNone(r['all_in_realized_net_pnl_eur'])
        wallet['closed'][0]['profit']=100
        self.assertIsNone(v.wallet_outcomes(wallet)['modeled_realized_net_pnl_eur'])

    def test_unknown_price_and_incomplete_equity_not_positive_results(self):
        wallet={'cash':90,'reserve':0,'positions':[{'quote_status':'UNKNOWN'}],
                'closed':[{'profit':10}], 'observations':[{'valuation_complete':False,'estimated_equity':110}]}
        r=v.wallet_outcomes(wallet)
        self.assertIsNone(r['estimated_equity_eur']); self.assertIsNone(r['modeled_realized_net_pnl_eur'])

    def test_report_persists_and_requires_wallet_evidence(self):
        with self.assertRaises(FileNotFoundError): v.write_report(self.t)
        for path in v.WALLETS.values():
            with open(path,'w') as f: json.dump({'cash':100,'reserve':0,'positions':[],'closed':[],
                'observations':[{'at':self.t.isoformat(),'valuation_complete':True,'unverified_quotes':0,'estimated_equity':100}]},f)
        r=v.write_report(self.t)
        self.assertEqual(r['relative_modeled_equity_eur'],0)
        self.assertIsNone(r['forward_horizons_minutes']['5']['mean_observed_return_pct'])
        self.assertFalse(r['profitability_demonstrated']); self.assertFalse(r['execution_verified'])
        self.assertEqual(json.load(open(v.REPORT))['forward_rejection_outcomes'],'integrated')

    def test_real_wallet_rejection_hook_and_report_end_to_end(self):
        token=brain.analizar_par(pair(address='Mint',pool='Pool'))
        token['score']=2
        token['received_at']=datetime.now(timezone.utc).isoformat()
        with patch.dict(os.environ,{'BRAIN_V12_OBSERVABILITY':'1','BRAIN_QUOTE_GUARD':'0'}), \
             patch.object(brain,'cotizar_posicion',return_value=(1,20000,pair(address='Mint',pool='Pool'))), \
             contextlib.redirect_stdout(io.StringIO()):
            for label,path in zip(v.LABELS,v.WALLETS.values()):
                brain.simular_cartera([token],path,label,entry_guard=lambda _: 'test reject')
            report=v.run(lambda _:self.token)
        self.assertEqual(len(v.read()['cases']),2)
        self.assertEqual(report['wallets']['CONTROL']['cash_eur'],100)
        self.assertEqual(report['wallets']['NET']['sale_legs'],0)

    def test_v11_wallets_are_in_exit_only_watchdog(self):
        for path in v.WALLETS.values():
            with open(path, 'w') as handle:
                json.dump({'positions': [{'symbol': 'TEST'}]}, handle)
        with patch.dict(os.environ, {'BRAIN_V11_NET_LAB': '1'}), \
             patch.object(brain, 'simular_cartera') as simulate, \
             contextlib.redirect_stdout(io.StringIO()):
            brain.refresh_open_positions()
        self.assertEqual({call.args[1] for call in simulate.call_args_list}, set(v.WALLETS.values()))
        self.assertTrue(all(call.args[0] == [] for call in simulate.call_args_list))

    def test_research_quote_rejects_pair_migration_without_mutating_token(self):
        before=copy.deepcopy(self.token)
        with patch.object(brain,'cotizar_posicion',return_value=(1,20000,pair(address='Mint',pool='Other'))):
            with self.assertRaises(ValueError): brain.v12_quote(self.token)
        self.assertEqual(self.token,before)


if __name__=='__main__': unittest.main()

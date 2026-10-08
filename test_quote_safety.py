import unittest
import copy
import os
import tempfile
import json
import io
import contextlib
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
import quote_safety as q
from test_fomo_v8 import b, pair

class SafetyTests(unittest.TestCase):
    def setUp(self):
        q.FEE_CACHE.clear()
    def pool(self, price):
        return {'data': {'id':'solana_Pool','attributes':{'address':'Pool','base_token_price_usd':str(price)},'relationships':{'base_token':{'data':{'id':'solana_Token'}}}}}
    def test_extreme_not_ordinary_stop(self):
        self.assertTrue(q.extreme(.0000002887,.0007065))
        self.assertFalse(q.extreme(.8,1))
        self.assertTrue(q.extreme(5,1))
        self.assertTrue(q.extreme(.70,1))
        self.assertFalse(q.extreme(.71,1))
        self.assertTrue(q.extreme(1.50,1))
        self.assertFalse(q.extreme(1.49,1))

    def test_repeated_price_never_claims_fresh_trade_and_history_is_bounded(self):
        pos={};market=pair();now=datetime(2026,10,8,tzinfo=timezone.utc)
        first=q.record_market_observation(pos,1,market,now)
        second=q.record_market_observation(pos,1,market,now+timedelta(seconds=120))
        self.assertIsNone(second['source_timestamp'])
        self.assertIsNone(second['market_data_age_seconds'])
        self.assertEqual(second['snapshot_unchanged_seconds'],120)
        self.assertEqual(second['price_unchanged_seconds'],120)
        changed=copy.deepcopy(market);changed['volume']['m5']+=1
        third=q.record_market_observation(pos,1,changed,now+timedelta(seconds=123))
        self.assertEqual(third['snapshot_unchanged_seconds'],0)
        self.assertEqual(third['price_unchanged_seconds'],123)
        for i in range(400):q.record_market_observation(pos,2,changed,now+timedelta(seconds=124+i))
        self.assertEqual(len(pos['quote_history']),360)
        self.assertEqual(pos['quote_audit']['price_unchanged_seconds'],399)

    def test_panda_sized_drop_is_corroborated_and_preserves_real_observed_loss(self):
        pos=b.analizar_par(pair())
        pos.update(quantity=1,mark_net=.99*.98,last_verified_price=1)
        with patch.dict(os.environ,{'BRAIN_QUOTE_GUARD':'1'}), \
             patch.object(b,'pedir_json',return_value={'pairs':[pair(price=.48)]}), \
             patch.object(q,'corroborate',return_value={'status':'COINCIDE'}) as crosscheck:
            price,_,_=b.cotizar_posicion(pos)
        crosscheck.assert_called_once()
        self.assertEqual(price,.48)
        self.assertTrue(pos['quote_history'][-1]['accepted'])
        self.assertIsNone(pos['quote_history'][-1]['market_data_age_seconds'])

    def test_moderate_discrepant_drop_keeps_previous_mark_and_records_rejected_price(self):
        pos=b.analizar_par(pair())
        pos.update(quantity=1,mark_net=.99*.98,last_verified_price=1)
        with patch.dict(os.environ,{'BRAIN_QUOTE_GUARD':'1'}), \
             patch.object(b,'pedir_json',return_value={'pairs':[pair(price=.48)]}), \
             patch.object(q,'corroborate',return_value={'status':'DISCREPANCIA'}):
            with self.assertRaises(ValueError):b.cotizar_posicion(pos)
        self.assertEqual(pos['last_verified_price'],1)
        self.assertEqual(pos['mark_net'],.99*.98)
        self.assertEqual(pos['quote_history'][-1]['price'],.48)
        self.assertFalse(pos['quote_history'][-1]['accepted'])
    def test_corroborate_identity_and_disagreement(self):
        pos={'chain':'solana','pair':'Pool','address':'Token'}
        self.assertEqual(q.corroborate(pos,.0000002887,lambda _:self.pool(.00058))['status'],'DISCREPANCIA')
        self.assertEqual(q.corroborate(pos,.0000002887,lambda _:self.pool(.00000029))['status'],'COINCIDE')
        bad=self.pool(1);bad['data']['relationships']['base_token']['data']['id']='solana_token'
        with self.assertRaises(ValueError):q.corroborate(pos,1,lambda _:bad)
    def fee_payload(self, rate='0', mutable='0'):
        return {'code':1,'result':{'Token':{'transfer_fee':{'current_fee_rate':{'fee_rate':rate}},'transfer_fee_upgradable':{'status':mutable}}}}
    def test_positive_mutable_and_missing_fees_block(self):
        t={'chain':'solana','address':'Token'}
        for payload in [self.fee_payload('.01'),self.fee_payload('0','1'),{'code':1,'result':{}}]:
            q.FEE_CACHE.clear()
            evidence,reason=q.entry_fees(t,lambda _:payload)
            self.assertIsNotNone(reason)
        q.FEE_CACHE.clear()
        e,r=q.entry_fees(t,lambda _:self.fee_payload());self.assertIsNone(r)
        self.assertEqual(e['transfer_fee_rate'],0)
    def absent_fee_payload(self):
        p=self.fee_payload();p['result']['Token']['transfer_fee']={};return p
    def absence_report(self):
        return {'mint':'Token','tokenProgram':'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb',
                'token':{'isInitialized':True},'token_extensions':{'transferFeeConfig':None}}
    def test_empty_fee_requires_exact_independent_absence(self):
        calls=[]
        def fetch(url):
            calls.append(url)
            return self.absence_report() if 'rugcheck' in url else self.absent_fee_payload()
        e,r=q.entry_fees({'chain':'solana','address':'Token'},fetch)
        self.assertIsNone(r);self.assertEqual(e['absence_crosscheck']['source'],'RugCheck')
        q.entry_fees({'chain':'solana','address':'Token'},fetch)
        self.assertEqual(len(calls),2)
    def test_empty_fee_missing_wrong_mint_or_present_extension_blocks(self):
        for report in [{},dict(self.absence_report(),mint='Other'),
                       dict(self.absence_report(),token_extensions={}),
                       dict(self.absence_report(),token_extensions={'transferFeeConfig':{'fee':0}}),
                       dict(self.absence_report(),tokenProgram='Unknown')]:
            q.FEE_CACHE.clear()
            e,r=q.entry_fees({'chain':'solana','address':'Token'},
                            lambda url: report if 'rugcheck' in url else self.absent_fee_payload())
            self.assertIsNotNone(r);self.assertEqual(e['status'],'SIN DATOS')
    def test_missing_fee_key_remains_unknown(self):
        p=self.fee_payload();del p['result']['Token']['transfer_fee']
        e,r=q.entry_fees({'chain':'solana','address':'Token'},lambda _:p)
        self.assertIsNotNone(r);self.assertEqual(e['status'],'SIN DATOS')
    def test_scheduled_positive_fee_blocks_even_if_current_zero(self):
        p=self.fee_payload();p['result']['Token']['transfer_fee']['scheduled_fee_rate']=[{'fee_rate':'.01'}]
        e,r=q.entry_fees({'chain':'solana','address':'Token'},lambda _:p)
        self.assertIsNotNone(r);self.assertTrue(e['scheduled_positive_fee'])
    def test_independent_failure_remains_unknown(self):
        def fetch(url):
            if 'rugcheck' in url:raise TimeoutError('timeout')
            return self.absent_fee_payload()
        e,r=q.entry_fees({'chain':'solana','address':'Token'},fetch)
        self.assertIsNotNone(r);self.assertNotIn('Token',q.FEE_CACHE)

    def test_other_chain_is_not_certified(self):
        e,r=q.entry_fees({'chain':'bsc'},lambda _:self.fail('network'))
        self.assertEqual(e['status'],'SIN COBERTURA')
    def test_success_cache_and_unknown_not_cached(self):
        t={'chain':'solana','address':'Token'};calls=[]
        def fetch(url):calls.append(url);return self.fee_payload()
        q.entry_fees(t,fetch);q.entry_fees(t,fetch);self.assertEqual(len(calls),1)
    def test_invalidate_final_entry_quote_preserves_security_cache(self):
        market='https://api.dexscreener.com/latest/dex/pairs/solana/p'
        fallback='https://api.dexscreener.com/token-pairs/v1/solana/a'
        b.JSON_CACHE.update({market:1,fallback:2,'security':3})
        b.invalidate_entry_quote({'chain':'solana','pair':'p','address':'a'})
        self.assertNotIn(market,b.JSON_CACHE);self.assertNotIn(fallback,b.JSON_CACHE)
        self.assertEqual(b.JSON_CACHE['security'],3);b.JSON_CACHE.clear()
    def final_entry_case(self, final_price, confirm=False):
        cwd=os.getcwd()
        with tempfile.TemporaryDirectory() as temp:
            try:
                os.chdir(temp)
                token=b.analizar_par(pair())
                with patch.dict(os.environ,{'BRAIN_QUOTE_GUARD':'1'}), \
                     patch.object(b,'cotizar_posicion',side_effect=[(1,20000,pair()),(final_price,20000,pair(price=final_price))]), \
                     patch.object(b,'motivo_entrada',return_value=None), \
                     patch.object(q,'entry_fees',return_value=({'status':'VERIFICADO'},None)), \
                     contextlib.redirect_stdout(io.StringIO()):
                    b.simular_cartera([token],confirm=confirm)
                with open(b.V10_FILE) as h:return json.load(h)
            finally:os.chdir(cwd)
    def test_entry_uses_post_security_price_and_audit(self):
        state=self.final_entry_case(1.03)
        self.assertAlmostEqual(state['positions'][0]['entry_price'],1.03)
        self.assertTrue(state['positions'][0]['entry_final_quote']['after_security_checks'])
        self.assertAlmostEqual(state['positions'][0]['quantity'],5/(1.03*1.02*1.01))
    def test_final_price_drift_blocks_without_spending(self):
        state=self.final_entry_case(1.10,confirm=True)
        self.assertEqual(state['cash'],100);self.assertEqual(state['positions'],[])
        self.assertTrue(any('precio final se aleja' in n for n in state['last_run_notes']))

    def test_confirmed_crash_remains_executable(self):
        pos=b.analizar_par(pair())
        pos.update(quantity=1,mark_net=.99*.98,last_verified_price=1)
        with patch.dict(os.environ,{'BRAIN_QUOTE_GUARD':'1'}),patch.object(b,'pedir_json',return_value={'pairs':[pair(price=.001)]}),patch.object(q,'corroborate',return_value={'status':'COINCIDE'}):
            price,liquidity,data=b.cotizar_posicion(pos)
        self.assertEqual(price,.001)
        self.assertEqual(pos['last_verified_price'],.001)
        self.assertEqual(pos['quote_source'],'DEX Screener')

    def test_discrepant_exit_preserves_cash_and_flags_indicative_loss(self):
        cwd=os.getcwd()
        with tempfile.TemporaryDirectory() as temp:
            try:
                os.chdir(temp)
                token=b.analizar_par(pair())
                with patch.object(b,'cotizar_posicion',return_value=(1,20000,pair())),contextlib.redirect_stdout(io.StringIO()):
                    b.simular_cartera([token],confirm=False)
                with open(b.V10_FILE) as h:before=json.load(h)
                with patch.dict(os.environ,{'BRAIN_QUOTE_GUARD':'1'}),patch.object(b,'pedir_json',return_value={'pairs':[pair(price=.001)]}),patch.object(q,'corroborate',return_value={'status':'DISCREPANCIA'}),contextlib.redirect_stdout(io.StringIO()):
                    b.simular_cartera([],confirm=False)
                with open(b.V10_FILE) as h:after=json.load(h)
                self.assertEqual(after['cash'],before['cash'])
                self.assertEqual(after['closed'],[])
                self.assertEqual(after['positions'][0]['quote_status'],'NO VERIFICABLE')
                self.assertLess(after['positions'][0]['indicative_mark_net'],.02)
                self.assertFalse(after['observations'][-1]['valuation_complete'])
            finally:os.chdir(cwd)

    def test_confirmed_panda_sized_stop_does_not_fabricate_fill_at_minus_15(self):
        before=self.final_entry_case(1)
        cwd=os.getcwd()
        with tempfile.TemporaryDirectory() as temp:
            try:
                os.chdir(temp)
                with open(b.V10_FILE,'w') as handle:json.dump(before,handle)
                with patch.dict(os.environ,{'BRAIN_QUOTE_GUARD':'1'}), \
                     patch.object(b,'pedir_json',return_value={'pairs':[pair(price=.48)]}), \
                     patch.object(q,'corroborate',return_value={'status':'COINCIDE'}), \
                     contextlib.redirect_stdout(io.StringIO()):
                    b.simular_cartera([],confirm=False)
                with open(b.V10_FILE) as handle:after=json.load(handle)
                expected=before['positions'][0]['quantity']*.48*.99*.98
                self.assertEqual(after['positions'],[])
                self.assertAlmostEqual(after['cash'],before['cash']+expected)
                sale=after['closed'][-1]
                self.assertEqual(sale['exit_reason'],'STOP -15%')
                self.assertAlmostEqual(sale['profit'],expected-5)
                self.assertLess(sale['last_pnl_net_pct'],-50)
                self.assertTrue(sale['quote_history'][-1]['accepted'])
                self.assertEqual(len(after['data_policy_history']),len(before['data_policy_history']))
            finally:os.chdir(cwd)

if __name__=='__main__':unittest.main()


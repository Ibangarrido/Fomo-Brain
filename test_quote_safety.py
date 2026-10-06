import unittest
import copy
import os
import tempfile
import json
import io
import contextlib
from unittest.mock import patch
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
    def test_other_chain_is_not_certified(self):
        e,r=q.entry_fees({'chain':'bsc'},lambda _:self.fail('network'))
        self.assertEqual(e['status'],'SIN COBERTURA')
    def test_success_cache_and_unknown_not_cached(self):
        t={'chain':'solana','address':'Token'};calls=[]
        def fetch(url):calls.append(url);return self.fee_payload()
        q.entry_fees(t,fetch);q.entry_fees(t,fetch);self.assertEqual(len(calls),1)
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

if __name__=='__main__':unittest.main()

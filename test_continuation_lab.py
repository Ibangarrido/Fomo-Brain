import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import fomo_brain as brain
import continuation_lab as lab
import candle_lab
from test_fomo_v8 import pair

class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.cwd=os.getcwd();os.chdir(self.tmp.name)
    def tearDown(self):
        os.chdir(self.cwd);self.tmp.cleanup()
    def read(self,path):
        with open(path) as f:return json.load(f)
    def bars(self):
        minute=int(datetime.now(timezone.utc).timestamp()//60)*60
        values=[(1,1.4,1,1.1,100),(1.1,1.3,1.05,1.2,100),(1.2,1.4,1.15,1.3,100),(1.3,1.32,1.2,1.22,100),(1.22,1.36,1.21,1.35,200)]
        return [[minute-300+i*60,*v] for i,v in enumerate(values)]
    def candidate(self):
        p=pair(address='cont',price=1.35,liquidity=25000)
        p['priceChange']={'h1':400,'m5':-10};p['txns']['m5']={'buys':55,'sells':45}
        p['_brain_received_at']=datetime.now(timezone.utc).isoformat()
        token=brain.analizar_par(p)
        old=dict(token,received_at=(datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat(),price=1.34)
        return p,token,old
    def test_bootstrap_once_and_incomplete_refuses_reset(self):
        self.assertTrue(lab.bootstrap());self.assertFalse(lab.bootstrap())
        for p in lab.LEGACY_FILES:self.assertEqual(self.read(p)['cash'],100)
        os.remove(lab.ARMS['50'][0])
        with self.assertRaises(ValueError):lab.bootstrap()
    def test_pattern_bootstrap_preserves_legacy_and_refuses_partial_reset(self):
        lab.bootstrap();path=lab.ARMS['50'][0];state=self.read(path);state['cash']=93
        with open(path,'w') as f:json.dump(state,f)
        self.assertTrue(lab.bootstrap_pattern());self.assertFalse(lab.bootstrap_pattern())
        self.assertEqual(self.read(path)['cash'],93)
        starts=[self.read(spec[0]) for spec in lab.PATTERN_ARMS.values()]
        self.assertEqual(starts[0]['pattern_baseline'],starts[1]['pattern_baseline'])
        self.assertTrue(all(s['cash']==100 and not s['positions'] for s in starts))
        os.remove(lab.PATTERN_ARMS['pattern_breakout'][0])
        with self.assertRaises(ValueError):lab.bootstrap_pattern()
    def breakout_bars(self):
        minute=int(datetime.now(timezone.utc).timestamp()//60)*60
        values=[(1,1.025,.99,1.02,100),(1.02,1.085,1.01,1.08,180),
                (1.08,1.09,1.06,1.075,80),(1.075,1.085,1.06,1.08,70),
                (1.08,1.12,1.07,1.115,220)]
        return [[minute-300+i*60,*v] for i,v in enumerate(values)]
    def test_breakout_arm_accepts_confirmed_pause_control_rejects(self):
        _,token,_=self.candidate();token['price']=1.115
        result={'bars':self.breakout_bars()}
        with patch.object(candle_lab,'context',return_value=result):
            self.assertIsNotNone(lab.guard(token))
            self.assertIsNone(lab.breakout_guard(token))
            self.assertEqual(token['continuation_pattern'],'CONSOLIDATION_BREAKOUT_WITH_VOLUME')
            token['price']=1.09;self.assertIsNotNone(lab.breakout_guard(token))
            token['price']=1.18;self.assertIsNotNone(lab.breakout_guard(token))
    def test_breakout_rejects_weak_volume_wick_falling_support_and_incomplete_bars(self):
        _,token,_=self.candidate();token['price']=1.115
        for mutate in (lambda b:b[-1].__setitem__(5,20),
                       lambda b:b[-1].__setitem__(2,1.3),
                       lambda b:b[-2].__setitem__(3,.98),
                       lambda b:b[-2].__setitem__(5,200),
                       lambda b:b[-1].__setitem__(0,b[-1][0]+60)):
            bars=self.breakout_bars();mutate(bars)
            with patch.object(candle_lab,'context',return_value={'bars':bars}):
                self.assertIsNotNone(lab.breakout_guard(token))
    def test_pattern_arms_skip_initial_cycle_then_use_distinct_guards(self):
        lab.bootstrap();calls=[]
        def simulator(ranking,path,label,**kwargs):
            calls.append((path,kwargs['entry_guard']))
            state=self.read(path);state['observations'].append({'verified_component':state['cash'],
                'estimated_equity':state['cash'],'open':0,'closed':0})
            with open(path,'w') as f:json.dump(state,f)
        with contextlib.redirect_stdout(io.StringIO()):lab.run([],simulator)
        self.assertEqual(len(calls),3)
        calls.clear()
        with contextlib.redirect_stdout(io.StringIO()):lab.run([],simulator)
        self.assertEqual(len(calls),5)
        self.assertIn((lab.PATTERN_ARMS['pattern_breakout'][0],lab.breakout_guard),calls)
        self.assertIn((lab.PATTERN_ARMS['pattern_pullback'][0],lab.guard),calls)
    def test_continuation_changes_policy_but_not_liquidity_or_confirmation(self):
        _,t,old=self.candidate()
        self.assertIn('75%',brain.motivo_entrada(t,True,min_buy_ratio=.75,previous_observation=old))
        self.assertIsNone(brain.motivo_entrada(t,True,'continuation',min_buy_ratio=.5,previous_observation=old))
        self.assertIn('60%',brain.motivo_entrada(t,True,'continuation',min_buy_ratio=.6,previous_observation=old))
        t['liquidity']=18000
        self.assertIn('liquidez',brain.motivo_entrada(t,True,'continuation',min_buy_ratio=.5,previous_observation=old))
        t['liquidity']=25000;old['received_at']=(datetime.now(timezone.utc)-timedelta(seconds=100)).isoformat()
        self.assertIn('confirmacion',brain.motivo_entrada(t,True,'continuation',min_buy_ratio=.5,previous_observation=old))
    def test_pullback_accepts_only_closed_volume_reclaim(self):
        _,t,_=self.candidate();bars=self.bars()
        result=candle_lab.evaluate_rows({'data':{'attributes':{'ohlcv_list':bars}}},datetime.now(timezone.utc).timestamp())
        self.assertEqual(result['pattern_research']['name'],'PULLBACK_RECLAIM_WITH_VOLUME')
        with patch.object(candle_lab,'context',return_value=result):
            self.assertIsNone(lab.guard(t));t['price']=1.3;self.assertIsNotNone(lab.guard(t))
        bars[-1][5]=10
        with patch.object(candle_lab,'context',return_value={'bars':bars}):self.assertIsNotNone(lab.guard(t))
        bars=self.bars();bars[-1][0]+=60
        with patch.object(candle_lab,'context',return_value={'bars':bars}):self.assertIsNotNone(lab.guard(t))
        with patch.object(candle_lab,'context',return_value={'status':'SIN DATOS'}):self.assertIsNotNone(lab.guard(t))
    def test_pullback_above_all_highs_is_not_lost_to_breakout_label(self):
        _,token,_=self.candidate();bars=self.bars()
        bars[-1][2]=1.46;bars[-1][4]=1.45;token['price']=1.45
        result=candle_lab.evaluate_rows({'data':{'attributes':{'ohlcv_list':bars}}},datetime.now(timezone.utc).timestamp())
        self.assertEqual(result['pattern_research']['name'],'BREAKOUT_WITH_VOLUME')
        for check in (lab.guard,lab.breakout_guard):
            with patch.object(candle_lab,'context',return_value=result):
                self.assertIsNone(check(token))
                self.assertEqual(token['continuation_pattern'],'PULLBACK_RECLAIM_WITH_VOLUME')
                token['price']=1.3;self.assertIsNotNone(check(token));token['price']=1.45
    def test_overlap_reclaim_still_rejects_deep_dip_weak_volume_lost_support_and_stale_bars(self):
        _,token,_=self.candidate();token['price']=1.45
        for mutate in (lambda b:b[-2].__setitem__(3,.9),
                       lambda b:b[-1].__setitem__(5,100),
                       lambda b:b[-1].__setitem__(3,1.1),
                       lambda b:b[-1].__setitem__(2,1.7),
                       lambda b:[row.__setitem__(0,row[0]-180) for row in b]):
            bars=self.bars();bars[-1][2]=1.46;bars[-1][4]=1.45;mutate(bars)
            with patch.object(candle_lab,'context',return_value={'bars':bars}):
                self.assertIsNotNone(lab.guard(token))
                self.assertIsNotNone(lab.breakout_guard(token))
    def test_isolated_fill_only_50_arm_and_first_read_does_not_fill(self):
        lab.bootstrap();p,t,old=self.candidate();key=t['chain']+':'+t['address']
        result=candle_lab.evaluate_rows({'data':{'attributes':{'ohlcv_list':self.bars()}}},datetime.now(timezone.utc).timestamp())
        for arm in ('50','60','control'):
            path,mode,ratio=lab.ARMS[arm];s=self.read(path);s['recovery_pending_signals']={key:old}
            with open(path,'w') as f:json.dump(s,f)
            with patch.object(brain,'cotizar_posicion',return_value=(1.35,25000,p)),patch.object(candle_lab,'context',return_value=result),patch.dict(os.environ,{'BRAIN_QUOTE_GUARD':'0'}),contextlib.redirect_stdout(io.StringIO()):
                brain.simular_cartera([t],path,confirm=True,entry_mode=mode,min_buy_ratio=ratio,entry_guard=lab.guard if mode=='continuation' else None)
            s=self.read(path);self.assertEqual(len(s['positions']),1 if arm=='50' else 0)
            self.assertEqual(s['cash'],95 if arm=='50' else 100)
        path,mode,ratio=lab.ARMS['50'];s=self.read(path);s['positions']=[];s['seen']=[];s['cash']=100;s['recovery_pending_signals']={}
        with open(path,'w') as f:json.dump(s,f)
        with patch.object(brain,'cotizar_posicion',return_value=(1.35,25000,p)),patch.dict(os.environ,{'BRAIN_QUOTE_GUARD':'0'}),contextlib.redirect_stdout(io.StringIO()):
            brain.simular_cartera([t],path,confirm=True,entry_mode=mode,min_buy_ratio=ratio,entry_guard=lab.guard)
        self.assertEqual(self.read(path)['cash'],100)
    def test_cannot_use_mode_in_original_wallet_or_without_guard(self):
        with self.assertRaises(ValueError):brain.simular_cartera([],entry_mode='continuation')
        lab.bootstrap();p,t,old=self.candidate()
        with self.assertRaises(ValueError):brain.simular_cartera([t],lab.ARMS['50'][0],entry_mode='continuation',min_buy_ratio=.5)
    def test_exit_only_includes_three_arms_and_never_creates_wallets(self):
        with patch.dict(os.environ,{'BRAIN_CONTINUATION_LAB':'1'}),contextlib.redirect_stdout(io.StringIO()):brain.refresh_open_positions()
        self.assertFalse(os.path.exists(lab.MARKER))

    def test_capital_brake_and_exit_watchdog_remain_active(self):
        lab.bootstrap();p,t,old=self.candidate();path,mode,ratio=lab.ARMS['50']
        s=self.read(path);s['cash']=70
        with open(path,'w') as f:json.dump(s,f)
        with patch.dict(os.environ,{'BRAIN_QUOTE_GUARD':'0'}),contextlib.redirect_stdout(io.StringIO()):
            brain.simular_cartera([t],path,confirm=True,entry_mode=mode,min_buy_ratio=ratio,entry_guard=lab.guard)
        self.assertEqual(self.read(path)['cash'],70)
        s=self.read(path);s['cash']=95;s['risk_control']={}
        s['positions']=[{'chain':'solana','address':'cont','pair':'p','symbol':'TEST',
                         'quantity':5,'budget':5,'entry_price':1,'peak_price':1,
                         'opened_at':datetime.now(timezone.utc).isoformat(),
                         'last_quote_at':datetime.now(timezone.utc).isoformat(),
                         'quote_status':'OK','mark_net':5,'partial_taken':False}]
        with open(path,'w') as f:json.dump(s,f)
        q=pair(address='cont',price=.5,liquidity=25000)
        with patch.object(brain,'cotizar_posicion',return_value=(.5,25000,q)),patch.dict(os.environ,{'BRAIN_CONTINUATION_LAB':'1','BRAIN_QUOTE_GUARD':'0'}),contextlib.redirect_stdout(io.StringIO()):
            brain.refresh_open_positions()
        self.assertEqual(len(self.read(path)['positions']),0)
        self.assertEqual(len(self.read(path)['closed']),1)
    def test_security_failure_blocks_paper_fill(self):
        lab.bootstrap();p,t,old=self.candidate();path,mode,ratio=lab.ARMS['50']
        s=self.read(path);s['recovery_pending_signals']={t['chain']+':'+t['address']:old}
        with open(path,'w') as f:json.dump(s,f)
        result=candle_lab.evaluate_rows({'data':{'attributes':{'ohlcv_list':self.bars()}}},datetime.now(timezone.utc).timestamp())
        with patch.object(brain,'cotizar_posicion',return_value=(1.35,25000,p)),patch.object(candle_lab,'context',return_value=result),patch('quote_safety.entry_fees',return_value=({},'security unavailable')),patch.dict(os.environ,{'BRAIN_QUOTE_GUARD':'1'}),contextlib.redirect_stdout(io.StringIO()):
            brain.simular_cartera([t],path,confirm=True,entry_mode=mode,min_buy_ratio=ratio,entry_guard=lab.guard)
        self.assertEqual(self.read(path)['cash'],100)

if __name__=='__main__':unittest.main()


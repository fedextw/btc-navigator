import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import numpy as np
import pandas as pd

from strategy_rules import candidate,prepare,resample_higher,PROFILES
from strategy_execution import eligible_time,exit_on_bar,settle_values
from strategy_journal import connect,process,summary,save_trade,state,DEFAULT_RISK
from strategy_learning import evidence,fit,predictions
from strategy_patterns import discover
from strategy_backtest import run
from market_data import demo_market


def frame(end='2026-10-23T00:00:00Z',count=300,interval='1h'):
    seconds=3600 if interval=='1h' else 900
    times=pd.date_range(end=pd.Timestamp(end),periods=count,freq=f'{seconds}s')
    return pd.DataFrame({'time':times,'open':100.,'high':101.,'low':99.,'close':100.,'volume':1000.,
        'close_time':times+pd.Timedelta(seconds=seconds)-pd.Timedelta(milliseconds=1)})


def row():
    return pd.Series(dict(close_time=pd.Timestamp('2026-10-23T11:59:59.999Z'),higher_time=pd.Timestamp('2026-10-23T11:59:59.999Z'),
        higher_ready=True,higher_trend='LONG',higher_adx=30.,higher_ema200=90.,regime='trend_up',trend='LONG',
        atr=1.,rsi=55.,macd_hist=.1,vwap=99.,prior_vwap=99.,prior_close=98.,close=100.,ema20=99.,ema50=97.,ema200=90.,
        volume_ratio=1.5,recent_pull_long=True,recent_pull_short=False,prior_high=99.,prior_low=97.,prior_low20=97.,prior_high20=101.,
        low=98.,high=101.,swing_low=99.,swing_high=101.,session_bars=8))


def plan(f,symbol='BTCUSDT',profile='trend'):
    r=row();r.close_time=f.iloc[-1].close_time;r.higher_time=r.close_time
    p=candidate(r,profile,symbol,'demo')
    # Wide levels isolate execution mechanics from the fixed strategy trigger.
    p.update(reference=100.,stop=95.,target=110.,atr=5.,max_bars=72)
    return p


def sample_trades(n=240):
    rows=[]
    for i in range(n):
        created=pd.Timestamp.now(tz='UTC').floor('D')-pd.Timedelta(days=1)-pd.Timedelta(hours=12*(n-1-i))
        r=plan(frame(end=created-pd.Timedelta(hours=1)),symbol='BTCUSDT')
        r['context']['indicators'].update(rsi=40+i%40,volume_ratio=1+i%7/10)
        win=i%10!=0
        r.update(id=f'fixture-{i}',mode='live',created_at=str(created),entry_time=str(created+pd.Timedelta(hours=2)),
            exit_time=str(created+pd.Timedelta(hours=8)),status='closed',pnl=2. if win else -1.,net_return=.02 if win else -.01,net_r=2. if win else -1.)
        rows.append(r)
    return rows


class RuleTests(unittest.TestCase):
    def test_distinct_profiles_and_explicit_prices(self):
        a=candidate(row(),'trend','BTCUSDT','demo');b=candidate(row(),'intraday','BTCUSDT','demo')
        self.assertEqual(a['side'],'LONG',a['checks']);self.assertEqual(b['side'],'LONG',b['checks'])
        self.assertEqual(a['interval'],'1h');self.assertEqual(b['interval'],'15m')
        self.assertAlmostEqual((a['target']-100)/(100-a['stop']),3.)
        self.assertAlmostEqual((b['target']-100)/(100-b['stop']),1.8)
        self.assertNotEqual(a['id'],b['id'])

    def test_high_volatility_or_missing_context_cannot_create_order(self):
        r=row();r.regime='high_volatility'
        self.assertEqual(candidate(r,'trend','BTCUSDT','demo')['side'],'WAIT')
        r=row();r.higher_ready=False
        self.assertEqual(candidate(r,'intraday','BTCUSDT','demo')['side'],'WAIT')

    def test_higher_timeframe_never_includes_unclosed_group(self):
        f=frame(count=1200)
        h=resample_higher(f,'4h')
        self.assertTrue((h.close_time<=f.iloc[-1].close_time).all())
        self.assertEqual(len(h),299)
        self.assertTrue((h.volume==4000).all())
        prepared=prepare(f,h)
        visible=prepared.dropna(subset=['higher_time'])
        self.assertTrue((visible.higher_time<=visible.close_time).all())

    def test_vwap_and_higher_alignment_are_causal(self):
        f=demo_market('BTCUSDT','15m',1500)['candles'];h=resample_higher(f,'1h')
        full=prepare(f,h);prefix=f.iloc[:1200]
        past=prepare(prefix,h)
        pd.testing.assert_frame_equal(full.iloc[:1200],past)


class ExecutionTests(unittest.TestCase):
    def test_never_fill_before_observation(self):
        observed=pd.Timestamp('2026-10-23T01:00:30Z')
        eligible=eligible_time('2026-10-23T00:59:59.999Z',observed,'1h')
        self.assertEqual(eligible,pd.Timestamp('2026-10-23T02:00:00Z'))
        self.assertGreater(eligible,observed)

    def test_both_stop_and_target_hit_is_loss_first(self):
        t=dict(side='LONG',stop=95.,target=110.,strategy='trend',bars_held=1,max_bars=72)
        b=pd.Series(dict(open=100.,low=94.,high=112.,close=105.))
        self.assertEqual(exit_on_bar(t,b),(95.,'stop_both_hit'))
        t.update(side='SHORT',stop=105.,target=90.);b.update(pd.Series({'low':89.,'high':106.}))
        self.assertEqual(exit_on_bar(t,b),(105.,'stop_both_hit'))

    def test_stop_gap_is_not_filled_at_better_stop_price(self):
        t=dict(side='LONG',stop=95.,target=110.,strategy='trend',bars_held=1,max_bars=72)
        b=pd.Series(dict(open=90.,low=89.,high=100.,close=99.))
        self.assertEqual(exit_on_bar(t,b),(90.,'stop_gap'))

    def test_intraday_closes_at_taipei_midnight(self):
        t=dict(side='LONG',stop=95.,target=110.,strategy='intraday',bars_held=1,max_bars=8,entry_time='2026-10-23T15:00:00Z')
        b=pd.Series(dict(open=100.,low=99.,high=101.,close=100.5,close_time=pd.Timestamp('2026-10-23T15:59:59.999Z')))
        self.assertEqual(exit_on_bar(t,b),(100.5,'session_close'))

    def test_fees_slippage_and_signed_funding_are_explicit(self):
        t=dict(side='SHORT',entry=100.,entry_time='2026-10-23T00:00:00Z',fee_pct=.1,slippage_pct=.1,
            funding_pct_8h=.01,quantity=1.,risk_budget=5.)
        x=settle_values(t,90.,'2026-10-23T08:00:00Z')
        self.assertAlmostEqual(x['exit'],90.09)
        self.assertAlmostEqual(x['funding'],-.01)
        self.assertAlmostEqual(x['pnl'],9.91-.19009+.01)


class JournalTests(unittest.TestCase):
    def test_future_fill_and_settlement_persist_without_double_counting(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);f=frame();p=plan(f);observed=f.iloc[-1].close_time+pd.Timedelta(seconds=30)
            with patch('strategy_journal.candidate',return_value=p):process(db,f,f,'trend','BTCUSDT','demo',now=observed)
            saved=summary(db,'trend','demo')['rows'][0]
            self.assertEqual(saved['status'],'pending')
            self.assertLess(pd.Timestamp(saved['created_at']),pd.Timestamp(saved['eligible_entry_time']))
            later=frame(end='2026-10-23T01:00:00Z')
            with patch('strategy_journal.candidate',return_value=p):process(db,later,later,'trend','BTCUSDT','demo',now=later.iloc[-1].close_time+pd.Timedelta(seconds=2),allow_new=False)
            self.assertEqual(summary(db,'trend','demo')['rows'][0]['status'],'pending')
            filled=frame(end='2026-10-23T02:00:00Z');filled.loc[filled.index[-1],'high']=112.
            with patch('strategy_journal.candidate',return_value=p):process(db,filled,filled,'trend','BTCUSDT','demo',now=filled.iloc[-1].close_time+pd.Timedelta(seconds=2),allow_new=False)
            result=summary(db,'trend','demo');trade=result['rows'][0]
            self.assertEqual(trade['status'],'closed')
            self.assertAlmostEqual(result['account']['equity'],10000+trade['pnl'])
            self.assertEqual(trade['reserved'],0.)
            db.close();db=connect(root)
            with patch('strategy_journal.candidate',return_value=p):process(db,filled,filled,'trend','BTCUSDT','demo',now=filled.iloc[-1].close_time+pd.Timedelta(seconds=3),allow_new=False)
            self.assertAlmostEqual(summary(db,'trend','demo')['account']['equity'],result['account']['equity'])
            db.close()

    def test_position_limit_and_accounts_are_separate(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);f=frame();now=f.iloc[-1].close_time+pd.Timedelta(seconds=30)
            for symbol in ('BTCUSDT','ETHUSDT'):
                with patch('strategy_journal.candidate',return_value=plan(f,symbol)):process(db,f,f,'trend',symbol,'demo',risk={'max_positions':1},now=now)
            rows=summary(db,'trend','demo')['rows']
            self.assertEqual([r['status'] for r in rows].count('pending'),1)
            self.assertEqual([r['status'] for r in rows].count('blocked'),1)
            self.assertIsNone(summary(db,'intraday','demo')['account']);db.close()

    def test_missing_entry_window_freezes_capital_instead_of_inventing_result(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);f=frame();p=plan(f)
            with patch('strategy_journal.candidate',return_value=p):process(db,f,f,'trend','BTCUSDT','demo',now=f.iloc[-1].close_time+pd.Timedelta(seconds=30))
            far=frame(end='2026-11-23T00:00:00Z')
            with patch('strategy_journal.candidate',return_value=p):process(db,far,far,'trend','BTCUSDT','demo',now=far.iloc[-1].close_time+pd.Timedelta(seconds=30),allow_new=False)
            stats=summary(db,'trend','demo')
            self.assertEqual(stats['unresolved'],1);self.assertGreater(stats['rows'][0]['reserved'],0)
            self.assertEqual(stats['closed'],0);self.assertEqual(stats['account']['equity'],10000)
            db.close()

    def test_historical_replay_never_populates_forward_journal(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root)
            report=run(demo_market('BTCUSDT','1h',1500)['candles'],'trend','BTCUSDT')
            self.assertEqual(report['source'],'historical_replay')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM strategy_trades').fetchone()[0],0);db.close()


class LearningTests(unittest.TestCase):
    def test_win_rate_is_reference_and_not_a_promotion_objective(self):
        rows=sample_trades(100)
        for i,r in enumerate(rows):r.update(pnl=2. if i<75 else -1.,net_return=.02 if i<75 else -.01)
        r=evidence(rows,'live')
        self.assertEqual(r['win_rate'],75.)
        self.assertFalse(r['target_pass']);self.assertFalse(r['checks']['逐筆1×回撤低於15%']);self.assertLess(r['wilson95_pct'][0],75.)
        self.assertTrue(evidence(sample_trades(100),'live')['target_pass'])
        self.assertFalse(evidence(sample_trades(100),'demo')['target_pass'])
        self.assertFalse(evidence(sample_trades(100),'live',unresolved=1)['target_pass'])

    def test_same_day_correlated_burst_does_not_qualify(self):
        rows=sample_trades(100)
        for r in rows:r['entry_time']='2026-10-23T01:00:00Z'
        self.assertFalse(evidence(rows,'live')['target_pass'])

    def test_strategy_fit_purges_labels_and_does_not_select_on_test_outcomes(self):
        rows=sample_trades(240)
        a=fit(rows,'trend','live')
        self.assertIsNotNone(a)
        split=a['split']
        self.assertLess(pd.Timestamp(split['train_last_outcome']),pd.Timestamp(split['validation_first_forecast']))
        self.assertLess(pd.Timestamp(split['validation_last_outcome']),pd.Timestamp(split['test_first_forecast']))
        changed=copy.deepcopy(rows)
        for r in changed[192:]:r['pnl']*=-1;r['net_return']*=-1
        b=fit(changed,'trend','live')
        self.assertEqual(a['model'],b['model']);self.assertEqual(a['threshold'],b['threshold'])
        self.assertTrue(a['shadow_only'])

    def test_predictions_reference_a_stored_version_and_do_not_rewrite_old_records(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);p=plan(frame())
            from strategy_learning import FEATURES
            model={'id':'fixture-model','threshold':.6,'model':{'mean':[0]*len(FEATURES),'scale':[1]*len(FEATURES),'weights':[0]*len(FEATURES),'bias':2}}
            state(db,'learner/trend/demo',{'incumbent':model})
            out=predictions(db,p)
            self.assertEqual(out[0]['model_id'],'fixture-model');self.assertTrue(out[0]['selected'])
            self.assertNotIn('win_rate',out[0]);db.close()

    def test_pattern_discovery_requires_future_data_and_chronological_confirmation(self):
        self.assertFalse(discover(sample_trades(30),'live')['patterns'])
        rows=sample_trades(100)
        report=discover(rows,'live')
        self.assertGreater(report['discovery_samples'],0);self.assertGreater(report['confirmation_samples'],0)
        self.assertTrue(all(not r['exploratory_support'] for r in discover(rows,'demo')['patterns']))
        historical=[{**r,'source':'historical_replay'} for r in rows]
        self.assertEqual(discover(historical,'live')['samples'],0)


class StrategyIntegrationTests(unittest.TestCase):
    def test_background_full_eligible_universe_and_cache(self):
        from test_monitor import FakeExchange
        from scanner import MarketScanner
        from signal_store import connect as signals_db,set_state
        from strategy_worker import cycle
        with tempfile.TemporaryDirectory() as root:
            client=FakeExchange(3);service=MarketScanner(root,client)
            db=signals_db(root)
            service.universe(db);service.batch_context(db);db.close()
            first=cycle(service,root)
            self.assertEqual(first['analyzed'],3,first)
            self.assertEqual(first['failed'],0,first)
            count=len(client.calls)
            second=cycle(service,root)
            self.assertEqual(second['analyzed'],3,second)
            self.assertEqual(len(client.calls),count)
            journal=connect(root)
            self.assertEqual(journal.execute('SELECT COUNT(*) FROM strategy_latest').fetchone()[0],6)
            journal.close()

    def test_ai_uses_pre_entry_snapshot_and_shared_quota_without_cloud_key(self):
        from signal_store import connect as signals_db
        from monitor_settings import save_settings
        from strategy_ai import generate
        with tempfile.TemporaryDirectory() as root:
            journal=connect(root);t=plan(frame());t.update(mode='live',status='pending',id='ai-fixture',created_at=str(pd.Timestamp.now(tz='UTC')),
                eligible_entry_time=str(pd.Timestamp.now(tz='UTC')+pd.Timedelta(hours=1)),analysis_context={'news':[{'title':'known-before-entry','url':'https://example.com','source':'fixture'}],'market':{}})
            save_trade(journal,t);journal.commit();journal.close()
            save_settings({'auto_ai_enabled':True,'strategy_ai_enabled':True,'ai_daily_limit':1},root)
            db=signals_db(root);summary_model=Mock(return_value='紙上策略研究')
            with patch('strategy_ai.load_credentials',side_effect=AssertionError('local provider must not access cloud credentials')):
                self.assertEqual(generate(db,root,summary_model),'complete')
            data=summary_model.call_args.args[1]['strategy_context']
            self.assertEqual(data['reference'],100.)
            self.assertNotIn('pnl',data);self.assertNotIn('exit',data)
            self.assertEqual(summary_model.call_args.args[2][0]['title'],'known-before-entry')
            self.assertEqual(generate(db,root,summary_model),'daily_limit')
            self.assertEqual(summary_model.call_count,1)
            db.close()

    def test_verified_alert_requires_explicit_opt_in_fresh_quote_and_deduplicates(self):
        import time
        from strategy_alerts import emit
        from signal_store import connect as signals_db,save_result
        from monitor_settings import load_settings,save_settings
        with tempfile.TemporaryDirectory() as root:
            journal=connect(root);signals=signals_db(root);now=time.time()
            t=plan(frame());t.update(mode='live',status='pending',id='alert-fixture',eligible_entry_time=str(pd.Timestamp(now+600,unit='s',tz='UTC')),
                model_predictions=[{'model_id':'shadow-model','selected':True}])
            save_trade(journal,t)
            for sample in sample_trades(100):
                sample['model_predictions']=[{'model_id':'shadow-model','selected':True}]
                save_trade(journal,sample)
            journal.commit()
            state(journal,'learner/trend/live',{'incumbent':{'id':'shadow-model'},'forward_evidence':{'target_pass':True,'samples':100,'trading_days':20,'win_rate':90}})
            save_result(signals,{'symbol':'BTCUSDT','interval':'1h','mode':'live','updated_at':str(pd.Timestamp.now(tz='UTC')),'side':'WAIT','score':0,'mark_price':100.,'mark_time':now});signals.commit()
            self.assertIsNone(emit(journal,signals,t,load_settings(root),now))
            settings=save_settings({'strategy_notifications':True,'notifications_enabled':True,'channel':'telegram'},root)
            self.assertIsNotNone(emit(journal,signals,t,settings,now))
            self.assertIsNone(emit(journal,signals,t,settings,now))
            event=json.loads(signals.execute('SELECT payload FROM events').fetchone()[0])
            self.assertEqual(event['kind'],'strategy_signal')
            self.assertIsNone(event['model_probability'])
            # Cached success cannot bypass the rolling recency check.
            later=now+8*86400
            t['id']='later-fixture';t['eligible_entry_time']=str(pd.Timestamp(later+600,unit='s',tz='UTC'))
            save_trade(journal,t);journal.commit()
            save_result(signals,{'symbol':'BTCUSDT','interval':'1h','mode':'live','updated_at':str(pd.Timestamp(later,unit='s',tz='UTC')),'side':'WAIT','score':0,'mark_price':100.,'mark_time':later});signals.commit()
            self.assertIsNone(emit(journal,signals,t,settings,later))
            # No actual Telegram transport is used.
            signals.close();journal.close()

    def test_strategy_learning_never_fits_on_tiny_sample_or_backfills_predictions(self):
        from strategy_learning import update
        with tempfile.TemporaryDirectory() as root:
            db=connect(root)
            for t in sample_trades(30):save_trade(db,t)
            db.commit()
            learner=update(db,'trend','live')
            self.assertNotIn('incumbent',learner)
            self.assertEqual(learner['closed_samples'],30)
            saved=json.loads(db.execute('SELECT payload FROM strategy_trades LIMIT 1').fetchone()[0])
            self.assertNotIn('model_predictions',saved);db.close()

    def test_first_strategy_model_is_archived_without_hindsight_predictions(self):
        from strategy_learning import update,selected_forward
        with tempfile.TemporaryDirectory() as root:
            db=connect(root)
            for t in sample_trades(240):save_trade(db,t)
            db.commit();learner=update(db,'trend','live')
            self.assertIn('incumbent',learner)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM strategy_models').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM strategy_training_runs').fetchone()[0],1)
            rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM strategy_trades')]
            self.assertEqual(selected_forward(rows,learner['incumbent']['id']),[])
            self.assertFalse(learner.get('forward_evidence',{}).get('target_pass',False));db.close()

    def test_equal_challenger_does_not_replace_incumbent(self):
        from strategy_learning import update
        with tempfile.TemporaryDirectory() as root:
            db=connect(root)
            for t in sample_trades(200):
                t['model_predictions']=[{'model_id':'old','selected':True},{'model_id':'new','selected':True}]
                save_trade(db,t)
            db.commit()
            state(db,'learner/trend/live',{'incumbent':{'id':'old'},'challenger':{'id':'new'},
                'last_attempt':str(pd.Timestamp.now(tz='UTC')),'last_source_count':200})
            learner=update(db,'trend','live')
            self.assertEqual(learner['incumbent']['id'],'old');self.assertNotIn('challenger',learner)
            self.assertEqual(learner['history'][-1]['decision'],'保留影子模型');db.close()

    def test_daily_confirmed_loss_guard_blocks_new_candidate(self):
        from strategy_journal import save_account
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);f=frame();p=plan(f);now=f.iloc[-1].close_time+pd.Timedelta(seconds=30)
            save_account(db,{'strategy':'trend','mode':'demo','initial':10000.,'equity':9700.,'peak':10000.,'max_drawdown_pct':3.,
                'day':now.tz_convert('Asia/Taipei').strftime('%Y-%m-%d'),'day_start':10000.,'created_at':str(now)})
            db.commit()
            with patch('strategy_journal.candidate',return_value=p):process(db,f,f,'trend','BTCUSDT','demo',now=now)
            trade=summary(db,'trend','demo')['rows'][0]
            self.assertEqual(trade['status'],'blocked');self.assertIn('損失上限',trade['reason'])
            self.assertEqual(trade['reserved'],0);db.close()

    def test_continuous_history_can_recover_unknown_without_rewriting_forecast(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);f=frame();p=plan(f);observed=f.iloc[-1].close_time+pd.Timedelta(seconds=30)
            with patch('strategy_journal.candidate',return_value=p):process(db,f,f,'trend','BTCUSDT','demo',now=observed)
            original=summary(db,'trend','demo')['rows'][0]
            far=frame(end='2026-11-23T00:00:00Z')
            with patch('strategy_journal.candidate',return_value=p):process(db,far,far,'trend','BTCUSDT','demo',now=far.iloc[-1].close_time+pd.Timedelta(seconds=30),allow_new=False)
            self.assertEqual(summary(db,'trend','demo')['unresolved'],1)
            restored=frame(end='2026-10-23T03:00:00Z',count=1000)
            restored.loc[restored.time==pd.Timestamp('2026-10-23T02:00:00Z'),'high']=112.
            with patch('strategy_journal.candidate',return_value=p):process(db,restored,restored,'trend','BTCUSDT','demo',now=pd.Timestamp('2026-11-23T04:00:00Z'),allow_new=False)
            outcome=summary(db,'trend','demo');t=outcome['rows'][0]
            self.assertEqual(t['status'],'closed');self.assertIn('recovered_at',t)
            self.assertEqual(t['created_at'],original['created_at'])
            self.assertEqual(t['eligible_entry_time'],original['eligible_entry_time'])
            self.assertAlmostEqual(outcome['account']['equity'],10000+t['pnl']);db.close()

    def test_late_recovered_labels_are_not_available_to_earlier_validation(self):
        rows=sample_trades(240)
        for r in rows[:144]:r['settled_at']=str(pd.Timestamp.now(tz='UTC'))
        self.assertIsNone(fit(rows,'trend','live'))


class StrategyQualityTests(unittest.TestCase):
    def test_higher_timeframe_gaps_block_new_candidate_without_fake_context(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);f=frame();h=resample_higher(frame(count=1200),'4h')
            now=f.iloc[-1].close_time+pd.Timedelta(seconds=30)
            good=process(db,f,h,'trend','BTCUSDT','demo',now=now,allow_new=False)
            self.assertTrue(good['checks']['暖機與高週期資料完整'])
            bad=process(db,f,h.drop(index=100),'trend','BTCUSDT','demo',now=now,allow_new=False)
            self.assertFalse(bad['checks']['暖機與高週期資料完整'])
            self.assertEqual(bad['side'],'WAIT');db.close()

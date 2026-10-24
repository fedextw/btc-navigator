import copy
import json
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from test_strategies import sample_trades,frame,plan
from ai_context_features import extract
from ai_diagnostics import health,reliability,guard
from ai_model_lab import fit_family,forecast,FAMILIES,update_lab,load_lab
from strategy_journal import connect,save_trade,state
from strategy_learning import predictions


def context_rows(n=300):
    rows=sample_trades(n)
    for r in rows:
        now=pd.Timestamp(r['created_at'])
        r['analysis_context']={'news':[{'title':'ETF approval and inflow','url':'https://example.com/'+r['id'],'source':'fixture','published':str(now-pd.Timedelta(hours=1)),'observed_at':str(now-pd.Timedelta(minutes=30))}],
            'exchange':{'observed_at':str(now-pd.Timedelta(minutes=1)),'funding_pct':.01},
            'oi_snapshot':{'observed_at':str(now-pd.Timedelta(minutes=2)),'oi_change_pct':2.},
            'market_observed_at':str(now-pd.Timedelta(minutes=5)),
            'market':{'fetched_at':str(now-pd.Timedelta(minutes=5)),'data':{'Alternative.me':{'fear_greed':50,'as_of':str(now-pd.Timedelta(hours=8))}}}}
    return rows


class PointInTimeTests(unittest.TestCase):
    def test_future_news_funding_oi_and_context_are_not_features(self):
        r=context_rows()[0];base=extract(r)
        self.assertEqual(base['values']['news_available'],1)
        self.assertEqual(base['values']['funding_available'],1)
        later=str(pd.Timestamp(r['created_at'])+pd.Timedelta(seconds=1))
        r['analysis_context']['news'][0]['observed_at']=later
        r['analysis_context']['exchange']['observed_at']=later
        r['analysis_context']['oi_snapshot']['observed_at']=later
        r['analysis_context']['market_observed_at']=later
        data=extract(r)['values']
        self.assertEqual(data['news_available'],0);self.assertEqual(data['funding_available'],0)
        self.assertEqual(data['oi_available'],0);self.assertEqual(data['fear_available'],0)

    def test_late_published_and_stale_inputs_are_masked_not_imputed(self):
        r=context_rows()[0];now=pd.Timestamp(r['created_at'])
        r['analysis_context']['news'][0]['published']=str(now+pd.Timedelta(hours=1))
        r['analysis_context']['exchange']['observed_at']=str(now-pd.Timedelta(minutes=11))
        data=extract(r)['values'];self.assertEqual(data['news_count'],0);self.assertEqual(data['funding_available'],0)
        old=copy.deepcopy(r);old.pop('analysis_context')
        self.assertTrue(all(v==0 for v in extract(old)['values'].values()))

    def test_news_deduplicates_and_never_reads_exit_or_ai_prose(self):
        r=context_rows()[0];r['analysis_context']['news']*=4
        before=extract(r);r['pnl']=-1e6;r['ai_text']='guaranteed profit';r['exit']=999
        self.assertEqual(extract(r),before);self.assertEqual(before['values']['news_count'],.02)


class DiagnosticsTests(unittest.TestCase):
    def data(self):
        rows=sample_trades(120)
        for i,r in enumerate(rows):
            win=i<90;r.update(pnl=2. if win else -1.,net_return=.002 if win else -.0001,net_r=2. if win else -1.)
            r['model_predictions']=[{'model_id':'old','selected':True,'probability':.9,'raw_probability':.95,'calibrated':True}]
        return rows

    def test_recent_loss_regime_pauses_without_rewriting_forecasts(self):
        rows=self.data();before=copy.deepcopy(rows);h=health(rows,'old')
        self.assertTrue(h['pause_qualified']);self.assertEqual(h['status'],'degraded')
        self.assertTrue(guard(rows,'old',rows[-1])['blocked']);self.assertEqual(rows,before)

    def test_sparse_or_one_day_burst_is_not_sufficient_degradation_evidence(self):
        rows=self.data()[-30:]
        self.assertFalse(health(rows,'old')['pause_qualified'])
        rows=self.data()
        for r in rows:r['exit_time']=rows[-1]['exit_time']
        self.assertFalse(health(rows,'old')['pause_qualified'])

    def test_regime_specific_negative_evidence_avoids_that_regime_only(self):
        rows=sample_trades(120)
        for i,r in enumerate(rows):
            bad=i%3==0;r['context']['regime']='range' if bad else 'trend_up'
            r.update(pnl=-1. if bad else 2.,net_r=-1. if bad else 2.,net_return=-.001 if bad else .002)
            r['model_predictions']=[{'model_id':'a','selected':True,'probability':.7}]
        regimes={r['regime']:r for r in health(rows,'a')['regimes']}
        self.assertEqual(regimes['range']['state'],'avoid');self.assertEqual(regimes['trend_up']['state'],'supported')
        self.assertEqual(regimes['high_volatility']['state'],'observe')

    def test_reliability_uses_saved_predictions_not_current_model(self):
        rows=self.data();result=reliability(rows,'old')
        self.assertEqual(result['samples'],120);self.assertEqual(result['calibrated_samples'],120)
        self.assertAlmostEqual(result['bins'][-1]['觀察獲利比例'],.75)
        self.assertAlmostEqual(result['brier'],(90*.01+30*.81)/120)
        rows[0]['settled_at']=str(pd.Timestamp.now(tz='UTC')+pd.Timedelta(days=1))
        self.assertEqual(reliability(rows,'old')['samples'],119)

    def test_unfamiliar_regime_waits_even_if_global_model_has_positive_results(self):
        rows=sample_trades(100)
        for r in rows:r['model_predictions']=[{'model_id':'old','selected':True,'probability':.9}]
        candidate=copy.deepcopy(rows[-1]);candidate['context']['regime']='range'
        result=guard(rows,'old',candidate)
        self.assertTrue(result['blocked']);self.assertIn('此行情尚無足夠正向未來證據',result['reasons'])

    def test_uncertain_prediction_blocks_qualified_signal(self):
        r=sample_trades(1)[0];r['model_predictions']=[{'model_id':'a','selected':False,'abstained':True,'uncertainty':['unknown']}]
        self.assertTrue(guard([],'a',r)['blocked'])


class MultiFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=context_rows()
        cls.models={f:fit_family(cls.rows,'trend','live',f) for f in FAMILIES}

    def test_all_six_families_train_and_have_time_isolated_calibration(self):
        self.assertEqual(len(self.models),6)
        for family,model in self.models.items():
            self.assertIsNotNone(model,family);s=model['split']
            self.assertLess(pd.Timestamp(s['train_last_available']),pd.Timestamp(s['calibration_first']))
            self.assertLess(pd.Timestamp(s['calibration_last_available']),pd.Timestamp(s['validation_first']))
            self.assertLess(pd.Timestamp(s['validation_last_available']),pd.Timestamp(s['test_first']))
            self.assertIsNotNone(model['calibrator'],family)
            self.assertEqual(model['version'],'multi-family-v1')

    def test_test_labels_do_not_change_engine_calibration_or_threshold(self):
        altered=copy.deepcopy(self.rows)
        for r in altered[240:]:r['pnl']*=-1;r['net_r']*=-1;r['net_return']*=-1
        for family in ('technical-naive-bayes','context-logistic'):
            new=fit_family(altered,'trend','live',family);old=self.models[family]
            self.assertEqual(new['engine'],old['engine']);self.assertEqual(new['calibrator'],old['calibrator']);self.assertEqual(new['threshold'],old['threshold'])

    def test_specialist_abstains_on_unknown_regime_and_context_models_on_missing_context(self):
        r=copy.deepcopy(self.rows[-1]);r['context']['regime']='range'
        p=forecast(self.models['regime-logistic'],r);self.assertTrue(p['abstained']);self.assertFalse(p['selected'])
        r=copy.deepcopy(self.rows[-1]);r['analysis_context']={}
        p=forecast(self.models['context-logistic'],r);self.assertTrue(p['abstained']);self.assertFalse(p['selected'])

    def test_low_win_rate_positive_expectancy_is_not_rejected_by_a_high_probability_floor(self):
        rows=copy.deepcopy(self.rows)
        for i,r in enumerate(rows):
            win=i%4==0;r.update(pnl=4. if win else -.5,net_r=4. if win else -.5,net_return=.004 if win else -.0005)
        model=fit_family(rows,'trend','live','technical-logistic')
        self.assertIsNotNone(model)
        self.assertLess(model['threshold'],.5)
        self.assertGreater(model['test_stats']['expectancy_pct'],0)

    def test_context_family_waits_for_real_coverage(self):
        self.assertIsNone(fit_family(sample_trades(300),'trend','live','context-logistic'))
        self.assertIsNone(fit_family(self.rows[:200],'trend','live','technical-logistic'))
        historical=[{**r,'source':'historical_replay'} for r in self.rows]
        self.assertIsNone(fit_family(historical,'trend','live','technical-logistic'))

    def test_late_recovered_training_labels_cannot_cross_calibration_boundary(self):
        rows=copy.deepcopy(self.rows)
        for r in rows[:170]:r['settled_at']=rows[210]['created_at']
        self.assertIsNone(fit_family(rows,'trend','live','technical-logistic'))

    def test_archives_candidates_without_backfilling_and_prediction_dispatches(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root)
            for r in self.rows:save_trade(db,r)
            db.commit()
            # A real archived multi-family incumbent also remains supported.
            incumbent={**self.models['technical-logistic'],'id':'prior-incumbent'};state(db,'learner/trend/live',{'incumbent':incumbent})
            lab=update_lab(db,'trend','live')
            self.assertEqual(len(lab['contenders']),6)
            self.assertGreaterEqual(db.execute('SELECT COUNT(*) FROM strategy_models').fetchone()[0],6)
            saved=json.loads(db.execute('SELECT payload FROM strategy_trades LIMIT 1').fetchone()[0])
            self.assertNotIn('model_predictions',saved)
            # A fresh plan gets parallel forecasts, old records stay unchanged.
            fresh=copy.deepcopy(self.rows[-1]);fresh['mode']='live';fresh['strategy']='trend'
            preds=predictions(db,fresh);self.assertGreaterEqual(len(preds),6)
            self.assertTrue(all('raw_probability' in p for p in preds))
            again=update_lab(db,'trend','live');self.assertEqual(len(again['attempts']),len(lab['attempts']))
            db.close()

    def test_identical_incumbent_is_not_its_own_contender(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root)
            for r in self.rows:save_trade(db,r)
            db.commit();state(db,'learner/trend/live',{'incumbent':self.models['technical-logistic']})
            lab=update_lab(db,'trend','live')
            self.assertNotIn(self.models['technical-logistic']['id'],[m['id'] for m in lab['contenders']]);db.close()

    def test_multi_family_round_promotes_only_after_all_common_future_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);contenders=[{**m,'id':'candidate-'+family} for family,m in self.models.items()]
            rows=sample_trades(180)
            for r in rows:
                r['model_predictions']=[{'model_id':'old','selected':True,'probability':.9}]+[{'model_id':m['id'],'selected':r['pnl']>0,'probability':.9} for m in contenders]
                save_trade(db,r)
            db.commit();state(db,'learner/trend/live',{'incumbent':{'id':'old'}})
            state(db,'ai-lab/trend/live',{'contenders':contenders,'round_started':str(pd.Timestamp.now(tz='UTC'))})
            report=update_lab(db,'trend','live')
            saved=json.loads(db.execute("SELECT payload FROM strategy_state WHERE name='learner/trend/live'").fetchone()[0])
            self.assertNotEqual(saved['incumbent']['id'],'old')
            self.assertEqual(report['contenders'],[])
            self.assertEqual(report['round_history'][-1]['decision'],'晉升多模型候選')
            self.assertTrue(all(r['confidence_pct']>99 for r in report['round_history'][-1]['reports']))
            db.close()

    def test_degradation_stops_alert_even_when_long_window_profit_qualifies(self):
        import time
        from strategy_alerts import emit
        from strategy_learning import evidence
        from signal_store import connect as signals_db,save_result
        from monitor_settings import save_settings
        rows=DiagnosticsTests().data()
        self.assertTrue(evidence(rows,'live')['target_pass'])
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);signals=signals_db(root);now=time.time()
            for r in rows:save_trade(db,r)
            t=plan(frame());t.update(id='new-alert',mode='live',status='pending',eligible_entry_time=str(pd.Timestamp(now+600,unit='s',tz='UTC')),model_predictions=[{'model_id':'old','selected':True}])
            save_trade(db,t);db.commit();state(db,'learner/trend/live',{'incumbent':{'id':'old'}})
            save_result(signals,dict(symbol='BTCUSDT',interval='1h',mode='live',updated_at=str(pd.Timestamp.now(tz='UTC')),side='WAIT',score=0,mark_price=100.,mark_time=now));signals.commit()
            settings=save_settings({'strategy_notifications':True,'notifications_enabled':True,'channel':'telegram'},root)
            self.assertIsNone(emit(db,signals,t,settings,now));self.assertEqual(signals.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)
            signals.close();db.close()

    def test_queued_alert_is_suppressed_after_degradation_without_sending(self):
        import time
        from unittest.mock import Mock
        from signal_store import connect as signals_db,save_result
        from monitor_settings import save_settings
        from notifications import dispatch
        now=time.time()
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);signals=signals_db(root)
            for r in DiagnosticsTests().data():save_trade(db,r)
            t=plan(frame());t.update(id='queued',mode='live',status='pending',eligible_entry_time=str(pd.Timestamp(now+600,unit='s',tz='UTC')),model_predictions=[{'model_id':'old','selected':True}])
            save_trade(db,t);db.commit();state(db,'learner/trend/live',{'incumbent':{'id':'old'}})
            payload={**t,'kind':'strategy_signal','model_id':'old'}
            signals.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('queued-event',now,now+600,'BTCUSDT','1h','LONG','live',json.dumps(payload)));signals.commit()
            save_settings({'strategy_notifications':True,'notifications_enabled':True,'channel':'telegram'},root)
            sender=Mock()
            with patch('notifications.effective_credentials',return_value={'telegram_token':'test','telegram_chat':'test'}):
                result=dispatch(signals,root,now,sender)
            sender.assert_not_called();self.assertEqual(result['sent'],0)
            self.assertEqual(signals.execute('SELECT status FROM deliveries').fetchone()[0],'suppressed')
            signals.close();db.close()

import copy
import json
import tempfile
import time
import unittest
from unittest.mock import patch,Mock
import pandas as pd
from test_strategies import frame,plan
from strategy_journal import connect,process,save_trade,summary
from trade_review import review,track_excursion
from strategy_execution import settle_values
from signal_lifecycle import refresh,reference_status,delivery_allowed
from signal_store import connect as signals_db,set_state
from monitor_settings import save_settings


def pending(now):
    t=plan(frame());t.update(id='lifecycle-test',mode='live',status='pending',created_at=str(now),eligible_entry_time=str(now+pd.Timedelta(minutes=10)),model_predictions=[])
    return t


def quote(db,now,price='100'):
    set_state(db,'risk_quotes',{'mode':'live','marks':{'BTCUSDT':{'markPrice':price,'time':int(now.timestamp()*1000)}},'books':{}})


def sent_base(db,t,now):
    identity='strategy-'+t['id']
    db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',(identity,now.timestamp(),now.timestamp()+600,'BTCUSDT','1h','LONG','live',json.dumps({'kind':'strategy_signal','id':t['id']})))
    db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?,?,?)',(identity,'telegram','sent',1,0,now.timestamp(),None));db.commit()


class ReviewTests(unittest.TestCase):
    def test_cost_bridge_reconciles_both_directions(self):
        for side in ('LONG','SHORT'):
            d=1 if side=='LONG' else -1
            t=dict(side=side,entry=100*(1+d*.0002),raw_entry=100.,entry_time='2026-10-23T00:00:00Z',quantity=2.,reference=100.,atr=5.,fee_pct=.05,slippage_pct=.02,funding_pct_8h=.01,risk_budget=10.)
            t.update(settle_values(t,105 if d==1 else 95,'2026-10-23T08:00:00Z'),status='closed')
            b=review(t)['bridge'];self.assertAlmostEqual(b['差額'],0.)
            self.assertGreater(b['滑價損失'],0)

    def test_cost_flip_is_observation_not_direction_error(self):
        t=dict(side='LONG',entry=100.02,raw_entry=100.,entry_time='2026-10-23T00:00:00Z',quantity=1.,reference=100.,atr=5.,fee_pct=.05,slippage_pct=.02,funding_pct_8h=.01,risk_budget=10.)
        t.update(settle_values(t,100.01,'2026-10-23T00:05:00Z'),status='closed')
        r=review(t);self.assertIn('cost_flip',r['tags']);self.assertNotIn('adverse_exit',r['tags'])

    def test_exit_bar_future_high_does_not_invent_favorable_excursion(self):
        t=dict(side='LONG',entry=100.,quantity=1.,mfe_usdt=0.,mae_usdt=0.,excursion_complete=True,risk_budget=10.)
        bar=pd.Series(dict(time=pd.Timestamp('2026-10-23T00:00:00Z'),high=1000.,low=1.))
        track_excursion(t,bar,95.)
        self.assertEqual(t['mfe_usdt'],0);self.assertEqual(t['mae_usdt'],5)
        t.update(status='closed',exit_reason='stop_both_hit',pnl=-5.)
        self.assertIn('ambiguous_bar',review(t)['tags']);self.assertNotIn('giveback',review(t)['tags'])

    def test_complete_survived_bar_can_support_giveback_but_legacy_path_cannot(self):
        t=dict(side='LONG',entry=100.,quantity=1.,mfe_usdt=0.,mae_usdt=0.,excursion_complete=True,risk_budget=10.)
        bar=pd.Series(dict(time=pd.Timestamp('2026-10-23T00:00:00Z'),high=120.,low=98.))
        track_excursion(t,bar);t.update(status='closed',pnl=-5.)
        self.assertIn('giveback',review(t)['tags'])
        t['excursion_complete']=False
        self.assertNotIn('giveback',review(t)['tags']);self.assertIn('incomplete_path',review(t)['tags'])

    def test_old_closed_record_does_not_invent_raw_prices(self):
        t=dict(status='closed',side='LONG',entry=100.,exit=99.,pnl=-1.,exit_reason='stop_gap')
        before=copy.deepcopy(t);r=review(t)
        self.assertIsNone(r['bridge']);self.assertEqual(t,before);self.assertIn('gap_stop',r['tags'])


class LifecycleTests(unittest.TestCase):
    def test_new_paper_trade_records_created_fill_exit_once_across_restart(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);f=frame();p=plan(f);observed=f.iloc[-1].close_time+pd.Timedelta(seconds=30)
            with patch('strategy_journal.candidate',return_value=p):process(db,f,f,'trend','BTCUSDT','demo',now=observed)
            later=frame(end='2026-10-23T02:00:00Z');later.loc[later.index[-1],'high']=112.
            with patch('strategy_journal.candidate',return_value=p):process(db,later,later,'trend','BTCUSDT','demo',now=later.iloc[-1].close_time+pd.Timedelta(seconds=2),allow_new=False)
            kinds=[r[0] for r in db.execute('SELECT kind FROM strategy_lifecycle ORDER BY id')]
            self.assertEqual(kinds,['created','open','closed'])
            t=summary(db,'trend','demo')['rows'][0];self.assertAlmostEqual(t['post_trade_review']['bridge']['差額'],0.)
            equity=summary(db,'trend','demo')['account']['equity'];db.close();db=connect(root)
            with patch('strategy_journal.candidate',return_value=p):process(db,later,later,'trend','BTCUSDT','demo',now=later.iloc[-1].close_time+pd.Timedelta(seconds=3),allow_new=False)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM strategy_lifecycle').fetchone()[0],3)
            self.assertEqual(summary(db,'trend','demo')['account']['equity'],equity);db.close()

    def test_old_snapshot_is_not_fabricated_creation_history(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);t=pending(pd.Timestamp.now(tz='UTC'));save_trade(db,t);db.commit()
            self.assertEqual(db.execute('SELECT kind FROM strategy_lifecycle').fetchone()[0],'baseline')
            save_trade(db,t);db.commit();self.assertEqual(db.execute('SELECT COUNT(*) FROM strategy_lifecycle').fetchone()[0],1);db.close()

    def test_reference_can_pause_resume_expire_without_changing_paper_status(self):
        now=pd.Timestamp.now(tz='UTC')
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);s=signals_db(root);t=pending(now);save_trade(db,t);db.commit();quote(s,now)
            refresh(root,now);refresh(root,now+pd.Timedelta(seconds=1))
            set_state(s,'risk_quotes',{'mode':'live','marks':{},'books':{}});refresh(root,now+pd.Timedelta(seconds=2))
            quote(s,now+pd.Timedelta(seconds=3));refresh(root,now+pd.Timedelta(seconds=3))
            refresh(root,now+pd.Timedelta(minutes=11))
            kinds=[r[0] for r in db.execute("SELECT kind FROM strategy_lifecycle WHERE kind LIKE 'reference_%' ORDER BY id")]
            self.assertEqual(kinds,['reference_valid','reference_paused','reference_valid','reference_expired'])
            self.assertEqual(summary(db,'trend','live')['rows'][0]['status'],'pending')
            self.assertEqual(s.execute('SELECT COUNT(*) FROM events').fetchone()[0],0);s.close();db.close()

    def test_never_published_candidates_and_ambiguous_deliveries_never_notify(self):
        now=pd.Timestamp.now(tz='UTC')
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);s=signals_db(root);t=pending(now);save_trade(db,t);db.commit()
            save_settings({'notifications_enabled':True,'channel':'telegram'},root)
            refresh(root,now+pd.Timedelta(minutes=11))
            self.assertEqual(s.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)
            sent_base(s,t,now);s.execute("UPDATE deliveries SET status='unknown'");s.commit()
            refresh(root,now+pd.Timedelta(minutes=12))
            self.assertEqual(s.execute('SELECT COUNT(*) FROM events').fetchone()[0],1);s.close();db.close()

    def test_expiry_update_only_for_sent_signal_is_deduplicated_and_deliverable(self):
        from notifications import dispatch,format_signal
        now=pd.Timestamp.now(tz='UTC')
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);s=signals_db(root);t=pending(now);save_trade(db,t);db.commit();sent_base(s,t,now)
            save_settings({'notifications_enabled':True,'channel':'telegram'},root)
            later=now+pd.Timedelta(minutes=11);refresh(root,later);refresh(root,later)
            self.assertEqual(s.execute('SELECT COUNT(*) FROM events').fetchone()[0],2)
            payload=json.loads(s.execute("SELECT payload FROM events WHERE id LIKE 'lifecycle-%'").fetchone()[0])
            self.assertTrue(delivery_allowed(root,s,payload));self.assertIn('不是新下單指令',format_signal(payload))
            sender=Mock()
            with patch('notifications.effective_credentials',return_value={'telegram_token':'test','telegram_chat':'test'}):
                dispatch(s,root,later.timestamp(),sender);dispatch(s,root,later.timestamp(),sender)
            self.assertEqual(sender.call_count,1);s.close();db.close()

    def test_superseded_update_is_suppressed_before_sending(self):
        now=pd.Timestamp.now(tz='UTC')
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);s=signals_db(root);t=pending(now);save_trade(db,t);db.commit();sent_base(s,t,now)
            save_settings({'notifications_enabled':True,'channel':'telegram'},root)
            refresh(root,now)
            payload=json.loads(s.execute("SELECT payload FROM events WHERE id LIKE 'lifecycle-%'").fetchone()[0])
            pause_key='lifecycle-'+str(payload['lifecycle_id'])+'-'+t['id']
            s.execute('INSERT INTO deliveries VALUES (?,?,?,?,?,?,?)',(pause_key,'telegram','sent',1,0,now.timestamp(),None));s.commit()
            quote(s,now+pd.Timedelta(seconds=2));refresh(root,now+pd.Timedelta(seconds=2))
            self.assertEqual(s.execute('SELECT COUNT(*) FROM events').fetchone()[0],3)
            self.assertFalse(delivery_allowed(root,s,payload))
            save_settings({'strategy_lifecycle_notifications':False},root)
            fresh=json.loads(s.execute("SELECT payload FROM events WHERE id LIKE 'lifecycle-%' ORDER BY created_at DESC LIMIT 1").fetchone()[0])
            self.assertFalse(delivery_allowed(root,s,fresh));s.close();db.close()

    def test_restart_does_not_push_reference_expiry_that_is_already_hours_old(self):
        now=pd.Timestamp.now(tz='UTC')
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);s=signals_db(root);t=pending(now);save_trade(db,t);db.commit();sent_base(s,t,now)
            save_settings({'notifications_enabled':True,'channel':'telegram'},root)
            refresh(root,now+pd.Timedelta(hours=2))
            self.assertEqual(s.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM strategy_lifecycle WHERE kind='reference_expired'").fetchone()[0],1)
            s.close();db.close()

    def test_lifecycle_update_never_consumes_ai_quota(self):
        from automatic_ai import generate_pending
        with tempfile.TemporaryDirectory() as root:
            s=signals_db(root);now=time.time()
            s.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('lifecycle-only',now,now+600,'BTCUSDT','1h','LONG','live',json.dumps({'kind':'strategy_lifecycle'})));s.commit()
            save_settings({'auto_ai_enabled':True},root);summarizer=Mock()
            self.assertEqual(generate_pending(s,root,summarizer),'no_pending_signal')
            summarizer.assert_not_called();self.assertEqual(s.execute('SELECT COUNT(*) FROM ai_reports').fetchone()[0],0);s.close()

    def test_status_update_does_not_restart_entry_signal_cooldown(self):
        from signal_store import record_signal
        from test_monitor import fixture_signal
        with tempfile.TemporaryDirectory() as root:
            s=signals_db(root);now=time.time()
            s.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('lifecycle-only',now,now+600,'BTCUSDT','1h','LONG','live',json.dumps({'kind':'strategy_lifecycle'})));s.commit()
            entry=record_signal(s,fixture_signal(symbol='BTCUSDT'),now=now);self.assertIsNotNone(entry)
            from scanner import MarketScanner
            from test_monitor import FakeExchange
            MarketScanner(root,FakeExchange(1)).universe(s)
            self.assertGreater(s.execute("SELECT expires_at FROM events WHERE id='lifecycle-only'").fetchone()[0],time.time())
            self.assertLessEqual(s.execute('SELECT expires_at FROM events WHERE id=?',(entry,)).fetchone()[0],time.time())
            s.close()

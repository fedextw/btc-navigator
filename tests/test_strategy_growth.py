"""Profit objectives must reject profitable-looking but unsupported upgrades."""
import copy
import json
import tempfile
import unittest
import pandas as pd
from strategy_growth import compare,forward_window,daily_interval
from strategy_learning import evidence,update
from strategy_journal import connect,save_trade,state
from test_strategies import sample_trades,frame,plan


class ProfitGrowthTests(unittest.TestCase):
    def test_low_win_rate_with_positive_risk_expectancy_can_qualify(self):
        rows=sample_trades(160)
        for i,r in enumerate(rows):
            win=i%4==0
            r.update(pnl=4. if win else -.5,net_return=.004 if win else -.0005,net_r=4. if win else -.5)
        result=evidence(rows,'live')
        self.assertEqual(result['win_rate'],25.)
        self.assertTrue(result['target_pass'],result['checks'])
        self.assertGreater(result['expectancy95_r'][0],0)

    def test_high_win_rate_with_negative_expectancy_is_rejected(self):
        rows=sample_trades(160)
        for i,r in enumerate(rows):
            win=i%10!=0
            r.update(pnl=.1 if win else -5.,net_return=.0001 if win else -.005,net_r=.1 if win else -5.)
        result=evidence(rows,'live')
        self.assertEqual(result['win_rate'],90.)
        self.assertFalse(result['target_pass'])

    def test_one_lucky_winner_cannot_establish_profit_evidence(self):
        rows=sample_trades(120)
        for r in rows:r.update(net_return=-.00001,pnl=-.01,net_r=-.01)
        rows[0].update(net_return=.2,pnl=200.,net_r=200.)
        self.assertFalse(evidence(rows,'live')['target_pass'])

    def test_future_settlement_and_unclosed_trades_never_enter_comparison(self):
        rows=sample_trades(100)
        for r in rows:r['model_predictions']=[{'model_id':'old','selected':True},{'model_id':'new','selected':True}]
        now=pd.Timestamp.now(tz='UTC')
        rows[0]['settled_at']=str(now+pd.Timedelta(days=1))
        rows[1]['status']='open'
        self.assertEqual(len(forward_window(rows,now)),98)
        self.assertEqual(compare(rows,'old','new','live',now=now)['common'],98)

    def test_competition_uses_shared_opportunities_and_zero_for_skipped(self):
        rows=sample_trades(200)
        for r in rows:
            r['model_predictions']=[{'model_id':'old','selected':True},{'model_id':'new','selected':r['pnl']>0}]
        result=compare(rows,'old','new','live')
        self.assertEqual(result['common'],len(forward_window(rows)))
        self.assertGreater(result['delta95_r'][0],0)
        self.assertTrue(result['comparison_pass'],result['checks'])
        old,new=result['models'].values()
        self.assertEqual(old['opportunities'],new['opportunities'])
        self.assertLess(new['selected'],old['selected'])
        self.assertGreater(new['total_r'],old['total_r'])
        self.assertFalse(compare(rows,'old','new','demo')['comparison_pass'])
        self.assertFalse(compare(rows,'old','new','live',unresolved=1)['comparison_pass'])

    def test_same_decisions_and_changes_to_position_size_do_not_fake_improvement(self):
        rows=sample_trades(120)
        for r in rows:r['model_predictions']=[{'model_id':'old','selected':True},{'model_id':'new','selected':True}]
        first=compare(rows,'old','new','live')
        for r in rows:r['pnl']*=100
        second=compare(rows,'old','new','live')
        self.assertEqual(first['delta95_r'],[0.,0.])
        self.assertEqual(first['curve'],second['curve'])
        self.assertFalse(second['comparison_pass'])

    def test_day_clustering_does_not_treat_one_day_as_hundreds_of_independent_days(self):
        rows=sample_trades(120)
        for r in rows:r['exit_time']=rows[-1]['exit_time']
        self.assertEqual(daily_interval(rows,[1.]*120),[None,None])
        self.assertFalse(evidence(rows,'live')['target_pass'])

    def test_supported_challenger_promotes_and_keeps_auditable_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(root)
            for r in sample_trades(180):
                r['model_predictions']=[{'model_id':'old','selected':True},{'model_id':'new','selected':r['pnl']>0}]
                save_trade(db,r)
            db.commit()
            state(db,'learner/trend/live',{'incumbent':{'id':'old'},'challenger':{'id':'new'},'last_source_count':180,'last_attempt':str(pd.Timestamp.now(tz='UTC'))})
            result=update(db,'trend','live')
            self.assertEqual(result['incumbent']['id'],'new')
            self.assertEqual(result['history'][-1]['decision'],'晉升影子模型')
            self.assertTrue(result['history'][-1]['comparison']['comparison_pass'])
            self.assertEqual(result['competition']['models']['現行模型']['model_id'],'old')
            db.close()

    def test_notification_does_not_relabel_old_qualification_as_new_profit_evidence(self):
        from notifications import format_signal
        proof=evidence(sample_trades(120),'live')
        event=dict(kind='strategy_signal',strategy='trend',symbol='BTCUSDT',interval='1h',side='LONG',entry=100.,target=110.,stop=95.,model_id='test',expires_at=pd.Timestamp.now(tz='UTC').timestamp()+600,forward_evidence=proof)
        self.assertIn('成本後逐筆平均',format_signal(event))
        self.assertIn('已通過獲利與風險研究門檻',format_signal(event))
        proof.pop('objective')
        self.assertIn('未重做新版獲利資格檢驗',format_signal(event))
        self.assertNotIn('已通過獲利與風險研究門檻',format_signal(event))

    def test_signal_chart_serializes_levels_and_brush_without_network(self):
        from strategy_growth_ui import signal_chart
        f=frame();trade=plan(f);trade.update(status='pending',created_at=trade['signal_time'])
        chart=signal_chart(f.tail(100),trade).to_dict()
        self.assertIn('vconcat',chart)
        serialized=json.dumps(chart,ensure_ascii=False)
        self.assertIn('signal_window',serialized)
        self.assertIn('止盈',serialized)
        self.assertIn('止損',serialized)

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from collector import connect as research_db
from learning_lab import model_path, save_record
from monitor_settings import DEFAULTS
from portfolio_replay import replay
from telemetry import training_activity, paper_totals, health_checks, journal_rows


def trade(symbol='BTCUSDT', side='LONG', start='2026-10-23T00:00:00+00:00', end='2026-10-23T08:00:00+00:00', entry=100, exit=110):
    return dict(symbol=symbol,side=side,entry_time=start,exit_time=end,entry=entry,exit=exit,status='closed')


class CostReplayTests(unittest.TestCase):
    def test_known_long_fee_and_funding(self):
        r=replay([trade()],1000,100,1,fee_pct=.1,slippage_pct=0,spread_pct=0,funding_pct_8h=.01)
        # Initial capital includes the entry fee; capital cannot be overspent.
        nominal=1000/1.001
        self.assertAlmostEqual(r['final'],1000+nominal*(.1-.0021-.0001))
        self.assertAlmostEqual(r['trades'][0]['notional']+r['trades'][0]['entry_fee'],1000)
        self.assertEqual(len(r['trades']),1)

    def test_short_receives_positive_funding(self):
        r=replay([trade(side='SHORT',exit=90)],1000,100,1,fee_pct=0,slippage_pct=0,spread_pct=0,funding_pct_8h=.01)
        self.assertAlmostEqual(r['final'],1100.1)

    def test_capital_reservations_and_concurrent_limit(self):
        r=replay([trade(),trade('ETHUSDT')],1000,60,5,0,0,0,0)
        self.assertEqual(len(r['trades']),1)
        self.assertEqual(r['skipped'],1)
        self.assertAlmostEqual(r['final'],1060)
        r=replay([trade(),trade('ETHUSDT')],1000,10,1,0,0,0,0)
        self.assertEqual(r['skipped'],1)

    def test_exit_releases_cash_before_next_entry(self):
        r=replay([trade(),trade('ETHUSDT',start='2026-10-23T08:00:00+00:00',end='2026-10-23T16:00:00+00:00')],1000,100,1,0,0,0,0)
        self.assertEqual(len(r['trades']),2)
        self.assertAlmostEqual(r['final'],1210)

    def test_cost_drag_and_no_reuse_of_original_net_return(self):
        original={**trade(),'net_return':999,'cost':99}
        cheap=replay([original],1000,100,1,0,0,0,0)
        costly=replay([original],1000,100,1,.1,.1,.1,.01)
        self.assertAlmostEqual(cheap['final'],1100)
        self.assertLess(costly['final'],cheap['final'])
        self.assertEqual(original['net_return'],999)

    def test_invalid_and_unresolved_excluded_and_drawdown(self):
        r=replay([trade(exit=90),{'status':'pending'},{**trade(),'entry':float('nan')}],1000,100,1,0,0,0,0)
        self.assertEqual(r['excluded'],2)
        self.assertAlmostEqual(r['realized_drawdown_pct'],10)
        with self.assertRaises(ValueError): replay([],initial=float('inf'))


class TelemetryTests(unittest.TestCase):
    def test_taipei_day_boundaries_and_read_only_runs(self):
        with tempfile.TemporaryDirectory() as root:
            db=research_db(root)
            report=json.dumps({'test_stats':{'trades':24,'net_pct':2,'max_drawdown_pct':1}})
            db.executemany('INSERT INTO training_runs VALUES (?,?,?,?,?,?,?)',[
                ('a','2026-10-23T15:59:59+00:00','BTCUSDT','1h','live',1,report),
                ('b','2026-10-23T16:00:00+00:00','BTCUSDT','1h','live',0,report),
                ('c','2026-10-23T17:00:00+00:00','BTCUSDT','1h','demo',1,report)])
            db.commit();db.close()
            r=training_activity(root,now=datetime(2026,10,24,12,tzinfo=ZoneInfo('Asia/Taipei')))
            self.assertEqual(r['today'],1)
            self.assertEqual(r['today_passed'],0)
            self.assertEqual(len(r['recent']),2)
            self.assertEqual(sum(d['訓練完成'] for d in r['days']),2)

    def test_no_fake_health_when_stale_or_service_disabled(self):
        r=health_checks({'updated_at':100,'status':'完成'},{},{},DEFAULTS,now=500)
        self.assertFalse(r[0]['ok'])
        self.assertIsNone(r[1]['ok'])
        r=health_checks({'updated_at':600,'status':'完成'},{},{},DEFAULTS,now=500)
        self.assertFalse(r[0]['ok'])

    def test_paper_totals_do_not_compound_across_symbols(self):
        r=paper_totals([{'trades':2,'wins':1,'sum_net_returns':.02,'pending':1,'gross_profit':.04,'gross_loss':.02},
                        {'trades':1,'wins':1,'sum_net_returns':.01,'pending':2,'gross_profit':.01,'gross_loss':0}])
        self.assertEqual(r['trades'],3)
        self.assertAlmostEqual(r['average_pct'],1)
        self.assertAlmostEqual(r['profit_factor'],2.5)
        self.assertEqual(r['pending'],3)

    def test_journal_names_and_modes_are_separated(self):
        with tempfile.TemporaryDirectory() as root:
            for demo in (True,False):
                save_record(model_path(Path(root)/'paper','BTCUSDT','1h',demo),{'rows':[{'status':'closed','demo':demo}]})
            rows=journal_rows(root)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['symbol'],'BTCUSDT')
            self.assertFalse(rows[0]['demo'])

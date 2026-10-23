import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from analysis_engine import analyze
from decision_research import explain
from market_data import demo_market
from market_regime import classify, regime_frame
from multi_timeframe import compare
from walk_forward import evaluate


def trending(up=True):
    m=demo_market('BTCUSDT','1h')
    f=m['candles']; close=np.exp(np.linspace(np.log(20 if up else 100),np.log(100 if up else 20),len(f)))
    f['close']=close; f['open']=close*.999 if up else close*1.001
    f['high']=f[['open','close']].max(axis=1)*1.001
    f['low']=f[['open','close']].min(axis=1)*.999
    return m


class RegimeTests(unittest.TestCase):
    def test_trend_and_insufficient_labels(self):
        self.assertEqual(classify(trending()['candles'])['code'],'trend_up')
        self.assertEqual(classify(trending(False)['candles'])['code'],'trend_down')
        self.assertFalse(classify(trending()['candles'].tail(100))['ready'])

    def test_causal_prefix_invariance(self):
        f=demo_market('BTCUSDT','1h',1000)['candles']
        full=regime_frame(f)
        prefix=regime_frame(f.iloc[:800])
        pd.testing.assert_frame_equal(full.iloc[:800],prefix)

    def test_volatility_spike_is_not_sold_as_trend_confidence(self):
        f=trending()['candles']
        f.loc[f.index[-15:],'high']=f.close.tail(15)*1.25
        f.loc[f.index[-15:],'low']=f.close.tail(15)*.75
        self.assertEqual(classify(f)['code'],'high_volatility')
        self.assertNotIn('probability',classify(f))


class MultiPeriodTests(unittest.TestCase):
    def markets(self):
        return {p:demo_market('BTCUSDT',p) for p in ('15m','1h','4h')}

    def test_never_uses_later_short_timeframe_bars(self):
        markets=self.markets()
        asof=markets['1h']['candles'].iloc[-2].close_time
        original=compare(markets,asof,'demo')
        mutated=copy.deepcopy(markets)
        for m in mutated.values():
            mask=m['candles'].close_time>asof
            for key in ['open','high','low','close']:
                m['candles'].loc[mask,key]*=10
        self.assertEqual(original,compare(mutated,asof,'demo'))
        for row in original['rows']:
            if row['candle_time']:
                self.assertLessEqual(pd.Timestamp(row['candle_time']),asof)

    def test_mixed_sources_and_missing_timeframes_cannot_align(self):
        markets=self.markets();asof=markets['1h']['candles'].iloc[-1].close_time
        markets['4h']['mode']='live'
        report=compare(markets,asof,'demo')
        self.assertFalse(report['complete']);self.assertEqual(report['side'],'WAIT')
        self.assertFalse(compare({'1h':markets['1h']},asof,'demo')['complete'])
        markets['4h']['symbol']='ETHUSDT'
        with self.assertRaises(ValueError):compare(markets,asof,'demo')

    def test_stale_or_gapped_period_rejected(self):
        markets=self.markets();asof=markets['1h']['candles'].iloc[-1].close_time
        markets['4h']['candles']['time']-=pd.Timedelta(days=3)
        markets['4h']['candles']['close_time']-=pd.Timedelta(days=3)
        self.assertFalse(compare(markets,asof,'demo')['rows'][0]['valid'])


class WalkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candles=demo_market('BTCUSDT','1h',1500)['candles']
        cls.report=evaluate(cls.candles,'BTCUSDT','1h',demo=True)

    def test_all_boundaries_purged_and_tests_nonoverlapping(self):
        last=None
        for f in self.report['folds']:
            self.assertLess(pd.Timestamp(f['train_last_outcome']),pd.Timestamp(f['validation_first']))
            self.assertLess(pd.Timestamp(f['validation_last_outcome']),pd.Timestamp(f['test_first']))
            if last:self.assertLess(last,pd.Timestamp(f['test_first']))
            last=pd.Timestamp(f['test_last_outcome'])
        signals=[t['signal_time'] for t in self.report['trades']]
        self.assertEqual(len(signals),len(set(signals)))
        self.assertTrue(self.report['shadow_only'])
        self.assertFalse(self.report['evidence_pass'])
        json.dumps(self.report,allow_nan=False)

    def test_future_mutation_does_not_change_first_fold_fit_or_result(self):
        first=self.report['folds'][0]
        changed=self.candles.copy()
        mask=changed.close_time>pd.Timestamp(first['test_last_outcome'])
        for key in ['open','high','low','close']:changed.loc[mask,key]*=1.7
        again=evaluate(changed,'BTCUSDT','1h',demo=True)
        self.assertEqual(first,again['folds'][0])

    def test_regime_variant_is_fixed_subset_not_test_optimized(self):
        r=self.report
        self.assertEqual(sum(s['trades'] for s in r['regimes']),r['baseline']['trades'])
        subset=[t for t in r['trades'] if (t['regime']=='trend_up' and t['side']=='LONG') or (t['regime']=='trend_down' and t['side']=='SHORT')]
        self.assertEqual(len(subset),r['regime_filter']['trades'])
        self.assertLessEqual(r['regime_filter']['trades'],r['baseline']['trades'])
        self.assertTrue(all(f['threshold'] in (.55,.60,.65) for f in r['folds']))

    def test_gaps_do_not_produce_performance_report(self):
        with self.assertRaises(ValueError):evaluate(self.candles.drop(index=700),'BTCUSDT','1h')


class DecisionEvidenceTests(unittest.TestCase):
    def test_formal_signal_independent_of_failed_shadow(self):
        m=trending();m['mode']='live';analysis=analyze(m)
        snap={'symbol':'BTCUSDT','interval':'1h','mode':'live','updated_at':str(pd.Timestamp.now(tz='UTC')),
              'candle_time':str(m['candles'].iloc[-1].close_time),'side':'LONG','gates':{'fixture_base_gate':True}}
        decision=explain(m,analysis,snap)
        self.assertEqual(decision['formal_side'],'LONG')
        self.assertFalse(decision['shadow_ready'])
        stale={**snap,'updated_at':str(pd.Timestamp.now(tz='UTC')-pd.Timedelta(minutes=6))}
        self.assertEqual(explain(m,analysis,stale)['formal_side'],'WAIT')
        other={**snap,'candle_time':str(m['candles'].iloc[-2].close_time)}
        self.assertFalse(explain(m,analysis,other)['snapshot_matches'])

    def test_expired_signal_window_is_not_an_active_direction(self):
        m=trending();m['mode']='live';analysis=analyze(m)
        reference=m['candles'].iloc[-1].close_time
        now=reference+pd.Timedelta(minutes=70)
        snap={'symbol':'BTCUSDT','interval':'1h','mode':'live','updated_at':str(now),
              'candle_time':str(reference),'side':'LONG','gates':{'base_gate':True}}
        self.assertEqual(explain(m,analysis,snap,now=now)['formal_side'],'WAIT')
        self.assertFalse(explain(m,analysis,snap,now=now)['formal_gates']['原研究時窗仍有效'])

    def test_demo_never_becomes_formal_signal(self):
        m=trending();analysis=analyze(m)
        self.assertEqual(explain(m,analysis)['formal_side'],'WAIT')


class ResearchDataTests(unittest.TestCase):
    def test_live_failure_does_not_fall_back_to_synthetic(self):
        from research_data import load_bundle
        with tempfile.TemporaryDirectory() as root, patch('research_data.CLIENT.json',side_effect=RuntimeError('fixture')):
            markets,errors=load_bundle('BTCUSDT','live',root)
            self.assertFalse(markets)
            self.assertEqual(len(errors),3)


class BrushTests(unittest.TestCase):
    def test_valid_epoch_range_and_invalid_selection(self):
        from interactive_research import brush_bounds
        r=brush_bounds({'focus':{'time':[1700000000000,1700003600000]}})
        self.assertEqual((r[1]-r[0]).total_seconds(),3600)
        self.assertIsNone(brush_bounds({}))
        self.assertIsNone(brush_bounds({'focus':{'time':[2,1]}}))
        self.assertIsNone(brush_bounds({'focus':{'time':['bad','date']}}))


class ShadowSchedulingTests(unittest.TestCase):
    def test_two_symbol_budget_rotates_without_starvation(self):
        from scanner import MarketScanner
        from signal_store import connect, save_result, set_state
        now=str(pd.Timestamp.now(tz='UTC'))
        with tempfile.TemporaryDirectory() as root:
            db=connect(root)
            for symbol in ['AUSDT','BUSDT','CUSDT','DUSDT']:
                save_result(db,{'symbol':symbol,'interval':'1h','mode':'live','updated_at':now,'side':'LONG','score':4,'candle_time':now})
            db.commit()
            scanner=MarketScanner(root)
            called=[]
            def completed(db,symbol,interval,marks):
                called.append(symbol)
                set_state(db,f'research/{symbol}/{interval}/live',{'as_of':now,'complete':True})
            with patch.object(scanner,'collect_shadow',side_effect=completed):
                scanner.collect_qualified_shadow(db,'1h','live',{}, {'errors':[]})
                self.assertEqual(len(called),2)
                scanner.collect_qualified_shadow(db,'1h','live',{}, {'errors':[]})
                self.assertEqual(len(set(called)),4)
            db.close()

    def test_background_snapshot_enriches_event_without_changing_signal_or_citations(self):
        # Exchange responses are synthetic fixtures tagged live ONLY in this test.
        from test_monitor import FakeExchange, fixture_signal
        from scanner import MarketScanner
        from signal_store import connect, record_signal, get_state
        with tempfile.TemporaryDirectory() as root:
            db=connect(root)
            frame=demo_market('BTCUSDT','1h')['candles']
            stamp=str(frame.iloc[-1].close_time)
            db.execute('INSERT INTO scan_cache VALUES (?,?,?,?)',('BTCUSDT','1h','live',frame.to_json(orient='records',date_format='iso')))
            db.commit()
            identity=record_signal(db,fixture_signal(symbol='BTCUSDT',candle_time=stamp,ai_sources=[{'title':'preserve-citation'}]))
            client=FakeExchange(1); scanner=MarketScanner(root,client)
            scanner.collect_shadow(db,'BTCUSDT','1h',{})
            shadow=get_state(db,'research/BTCUSDT/1h/live')
            self.assertTrue(shadow['complete'])
            event=json.loads(db.execute('SELECT payload FROM events WHERE id=?',(identity,)).fetchone()[0])
            self.assertEqual(event['side'],'LONG')
            self.assertEqual(event['ai_sources'][0]['title'],'preserve-citation')
            self.assertTrue(event['multi_timeframe']['shadow_only'])
            count=len(client.calls)
            scanner.collect_shadow(db,'BTCUSDT','1h',{})
            self.assertEqual(len(client.calls),count)
            db.close()

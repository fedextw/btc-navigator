import copy
import tempfile
import time
import unittest
from unittest.mock import Mock,patch
import numpy as np
import pandas as pd
from strategy_risk import quote,value_positions,snapshot_cost,funding_history,correlation_pairs
from strategy_execution import settle_values
from strategy_journal import connect,process,summary
from test_strategies import frame,plan


def market(now=None):
    now=time.time() if now is None else now
    return {'markPrice':'100','time':now*1000},{'bidPrice':'99.9','askPrice':'100.1','bidQty':'100','askQty':'100','time':now*1000}


def holding(**changes):
    return dict(symbol='BTCUSDT',status='open',side='LONG',entry=90.,quantity=2.,stop=85.,fee_pct=.05,slippage_pct=.02,**changes)


class LiveRiskTests(unittest.TestCase):
    def test_quote_rejects_stale_future_crossed_and_nonfinite(self):
        now=time.time();mark,book=market(now)
        self.assertTrue(quote(mark,book,now)['book_valid'])
        self.assertIsNone(quote(mark,book,now+121)['mark'])
        self.assertIsNone(quote(mark,book,now-1)['mark'])
        for bad in [{'bidPrice':'102'},{'askQty':'0'},{'bidPrice':'nan'},{'time':(now-121)*1000}]:
            self.assertFalse(quote(mark,{**book,**bad},now)['book_valid'])

    def test_pnl_does_not_double_charge_entry_fee_or_mutate_realized_capital(self):
        now=time.time();m,b=market(now);account={'equity':9999.91};rows=[holding()];before=copy.deepcopy((account,rows))
        result=value_positions(rows,account,{'BTCUSDT':quote(m,b,now)},now)
        self.assertAlmostEqual(result['floating'],20-.1-.04)
        self.assertAlmostEqual(result['estimated_equity'],9999.91+19.86)
        self.assertEqual((account,rows),before)
        self.assertEqual(result['gross_exposure'],200.)

    def test_partial_unknown_does_not_become_zero_portfolio_risk(self):
        now=time.time();m,b=market(now)
        rows=[holding(),{**holding(),'symbol':'ETHUSDT','status':'unresolved'}]
        result=value_positions(rows,{'equity':10000},{'BTCUSDT':quote(m,b,now)},now)
        self.assertEqual(result['unknown'],1);self.assertIsNone(result['estimated_equity']);self.assertIsNone(result['gross_exposure'])
        self.assertGreater(result['known_exposure'],0)
        result=value_positions([holding()],{'equity':10000},{'BTCUSDT':quote(m,b,now)},now+121)
        self.assertIsNone(result['floating'])

    def test_pending_only_has_no_mark_exposure_and_short_direction_is_correct(self):
        now=time.time();m,b=market(now)
        result=value_positions([{**holding(),'status':'pending'}],{'equity':10000},{},now)
        self.assertEqual(result['gross_exposure'],0);self.assertEqual(result['estimated_equity'],10000)
        result=value_positions([{**holding(),'side':'SHORT'}],{'equity':10000},{'BTCUSDT':quote(m,b,now)},now)
        self.assertLess(result['floating'],0);self.assertEqual(result['short'],200.)

    def test_snapshot_spread_is_explicit_and_cannot_exceed_visible_liquidity(self):
        m,b=market();q=quote(m,b)
        cost,error=snapshot_cost(q,'LONG',.02,100,5,2)
        self.assertIsNone(error);self.assertAlmostEqual(cost['effective_slippage_pct'],.12)
        self.assertIsNotNone(snapshot_cost(q,'LONG',.02,100,5,101)[1])
        self.assertIsNotNone(snapshot_cost(q,'LONG',.02,90,1,1)[1])
        q['mark_time']-=121
        self.assertIsNotNone(snapshot_cost(q,'LONG',.02,100,5,2)[1])

    def test_new_cost_contract_and_missing_quote_guard_persist(self):
        for present in (True,False):
            with tempfile.TemporaryDirectory() as root:
                db=connect(root);f=frame(end=pd.Timestamp.now(tz='UTC').floor('h')-pd.Timedelta(hours=1));p=plan(f);p['mode']='live'
                m,b=market();q=quote(m,b) if present else None
                with patch('strategy_journal.candidate',return_value=p):
                    process(db,f,f,'trend','BTCUSDT','live',risk={'quote_costs':True},quote_context=q)
                row=summary(db,'trend','live')['rows'][0]
                self.assertEqual(row['status'],'pending' if present else 'blocked')
                if present:
                    self.assertEqual(row['execution_cost']['version'],'quote-snapshot-v1')
                    self.assertGreater(row['slippage_pct'],.02)
                else:self.assertEqual(row['reserved'],0.)
                db.close()

    def test_settled_funding_events_use_event_mark_and_boundary_without_rewriting_legacy(self):
        trade={**holding(),'entry':100.,'entry_time':'2026-10-23T00:00:00Z','funding_pct_8h':.01,'risk_budget':10.,'execution_cost':{'version':'quote-snapshot-v1'}}
        data={'symbol':'BTCUSDT','start':'2026-10-23T00:00:00Z','end':'2026-10-23T16:00:00Z','events':[
            {'time':'2026-10-23T00:00:00Z','rate':.9,'mark':100},
            {'time':'2026-10-23T08:00:00Z','rate':.001,'mark':110},
            {'time':'2026-10-23T16:00:00Z','rate':.9,'mark':100}]}
        result=settle_values(trade,105,'2026-10-23T08:00:00Z',data)
        self.assertAlmostEqual(result['funding'],.22);self.assertEqual(result['funding_source'],'public_settled_events')
        short=settle_values({**trade,'side':'SHORT'},105,'2026-10-23T08:00:00Z',data)
        self.assertAlmostEqual(short['funding'],-.22)
        legacy=settle_values({**trade,'execution_cost':{}},105,'2026-10-23T08:00:00Z',data)
        self.assertAlmostEqual(legacy['funding'],.02)
        self.assertEqual(legacy['funding_source'],'fixed_rate_estimate')
        incomplete={**data,'end':'2026-10-23T07:00:00Z'}
        self.assertEqual(settle_values(trade,105,'2026-10-23T08:00:00Z',incomplete)['funding_source'],'fixed_rate_estimate')

    def test_funding_history_rejects_truncation_invalid_rows_and_deduplicates(self):
        start=pd.Timestamp('2026-10-23T00:00:00Z');end=start+pd.Timedelta(hours=8)
        event={'symbol':'BTCUSDT','fundingTime':end.timestamp()*1000,'fundingRate':'0.001','markPrice':'100'}
        client=Mock();client.json.return_value=[event,event]
        self.assertEqual(len(funding_history(client,'BTCUSDT',start,end)['events']),1)
        client.json.return_value=[event]*1000
        with self.assertRaises(ValueError):funding_history(client,'BTCUSDT',start,end)
        client.json.return_value=[{**event,'markPrice':'nan'}]
        with self.assertRaises(ValueError):funding_history(client,'BTCUSDT',start,end)

    def test_correlation_requires_fresh_aligned_data_and_adjusts_for_direction(self):
        now=pd.Timestamp.now(tz='UTC');f=frame(end=now.floor('h')-pd.Timedelta(hours=1),count=80)
        f['close']=100*np.cumprod(1+np.sin(np.arange(80))*.01)
        rows=[holding(),{**holding(),'symbol':'ETHUSDT'}]
        pairs=correlation_pairs(rows,{'BTCUSDT':f,'ETHUSDT':f},now)
        self.assertTrue(pairs[0]['共同方向風險偏高'])
        rows[1]['side']='SHORT'
        self.assertFalse(correlation_pairs(rows,{'BTCUSDT':f,'ETHUSDT':f},now)[0]['共同方向風險偏高'])
        self.assertEqual(correlation_pairs(rows,{'BTCUSDT':f,'ETHUSDT':f},now+pd.Timedelta(hours=3)),[])

    def test_quote_worker_book_failure_retains_fresh_marks_and_clears_old_book(self):
        from risk_worker import collect,quotes
        m,b=market();m['symbol']='BTCUSDT';b['symbol']='BTCUSDT'
        client=Mock();client.json.side_effect=[[m],[b],[m],RuntimeError('test')]
        with tempfile.TemporaryDirectory() as root:
            collect(client,root);q,_=quotes(root);self.assertTrue(q['BTCUSDT']['book_valid'])
            collect(client,root);q,raw=quotes(root);self.assertIsNotNone(q['BTCUSDT']['mark']);self.assertFalse(q['BTCUSDT']['book_valid'])
            self.assertEqual(raw['error'],'RuntimeError')
            self.assertEqual(quotes(root,mode='demo')[0],{})

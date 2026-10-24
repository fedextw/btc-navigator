import tempfile
import time
import unittest
import pandas as pd
from trading_frontend import signal_state,candidate_cards,market_rows,watchlist
from signal_store import connect,set_state,save_result


class FrontendTests(unittest.TestCase):
    def candidate(self,**changes):
        return dict(id='a',strategy='trend',symbol='BTCUSDT',side='LONG',status='pending',reference=100.,created_at=str(pd.Timestamp.now(tz='UTC')),eligible_entry_time=str(pd.Timestamp.now(tz='UTC')+pd.Timedelta(hours=1)),**changes)

    def test_only_unexpired_pending_candidates_are_new_signals(self):
        t=self.candidate();now=pd.Timestamp.now(tz='UTC')
        rows=[(t,True),({**t,'status':'open','entry':100.},True),({**t,'eligible_entry_time':str(now-pd.Timedelta(seconds=1))},True)]
        self.assertEqual(len(candidate_cards(rows,now=now)),1)
        self.assertFalse(signal_state(rows[1][0],now)[3])
        self.assertFalse(signal_state(rows[2][0],now)[3])

    def test_filters_keep_research_candidates_distinct_from_verified(self):
        rows=[(self.candidate(),False)]
        self.assertEqual(len(candidate_cards(rows,query='btc')),1)
        self.assertFalse(candidate_cards(rows,direction='SHORT'))
        self.assertFalse(candidate_cards(rows,profile='intraday'))
        self.assertFalse(candidate_cards(rows,verified_only=True))
        self.assertFalse(candidate_cards([({**rows[0][0],'_front_blocked':'stale'},True)]))

    def test_market_covers_universe_not_just_scanned_symbols_and_rejects_stale_prices(self):
        now=time.time()
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);set_state(db,'universe',{'symbols':['BTCUSDT','NEWUSDT']})
            set_state(db,'risk_quotes',{'mode':'live','marks':{'BTCUSDT':{'markPrice':'100','time':now*1000},'NEWUSDT':{'markPrice':'50','time':(now-121)*1000}}})
            set_state(db,'tickers',{'fetched_at':now,'rows':{'NEWUSDT':{'priceChangePercent':'3','quoteVolume':'50000'}}})
            rows=market_rows(db,'live',now)
            self.assertEqual(len(rows),2);self.assertEqual(rows[0]['標記價格'],100)
            self.assertIsNone(rows[1]['標記價格']);self.assertEqual(rows[1]['24h漲跌%'],3.)
            self.assertIsNone(market_rows(db,'live',now+601)[1]['24h漲跌%'])
            db.close()

    def test_demo_does_not_relabel_live_quotes_as_demo(self):
        now=time.time()
        with tempfile.TemporaryDirectory() as root:
            db=connect(root);set_state(db,'universe',{'symbols':['BTCUSDT']});set_state(db,'risk_quotes',{'mode':'live','marks':{'BTCUSDT':{'markPrice':'100','time':now*1000}}})
            self.assertIsNone(market_rows(db,'demo',now)[0]['標記價格']);db.close()

    def test_watchlist_persists_without_accepting_paths(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(watchlist(root),[])
            self.assertEqual(watchlist(root,['BTCUSDT','BTCUSDT','../../AUSDT']),['BTCUSDT'])
            self.assertEqual(watchlist(root),['BTCUSDT'])

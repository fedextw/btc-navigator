import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from agent_history_backfill import backfill_once

class FakeClient:
    def __init__(self,rows):
        self.rows=rows
        self.calls=[]
    def json(self,path,params,weight):
        self.calls.append((path,params,weight))
        return self.rows

class BackfillTests(unittest.TestCase):
    def test_missing_database_never_calls_exchange(self):
        with tempfile.TemporaryDirectory() as d:
            client=FakeClient([])
            self.assertEqual(backfill_once(d,"BTCUSDT",client=client)["status"],"waiting_database")
            self.assertEqual(client.calls,[])

    def test_closed_candles_insert_once_and_open_bar_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            with closing(sqlite3.connect(state/"research.sqlite3")) as db:
                db.execute("CREATE TABLE candles(symbol TEXT,interval TEXT,mode TEXT,time TEXT PRIMARY KEY,close_time TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
            start=datetime(2026,10,1,tzinfo=timezone.utc)
            rows=[]
            for i in range(301):
                t=start+timedelta(hours=i)
                rows.append([int(t.timestamp()*1000),"100","110","90","105","3",int((t+timedelta(hours=1)).timestamp()*1000)-1])
            client=FakeClient(rows)
            now=start+timedelta(hours=300)
            first=backfill_once(d,"BTCUSDT",client=client,now=now)
            second=backfill_once(d,"BTCUSDT",client=client,now=now)
            self.assertEqual(first["inserted"],300)
            self.assertEqual(second["inserted"],0)
            with closing(sqlite3.connect(state/"research.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM candles").fetchone()[0],300)

    def test_reject_invalid_prices_without_partial_writes(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            with closing(sqlite3.connect(state/"research.sqlite3")) as db:
                db.execute("CREATE TABLE candles(symbol TEXT,interval TEXT,mode TEXT,time TEXT,close_time TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
            row=[1,"100","90","95","105","1",3600000]
            with self.assertRaises(ValueError):
                backfill_once(d,"BTCUSDT",client=FakeClient([row]))
            with closing(sqlite3.connect(state/"research.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM candles").fetchone()[0],0)

if __name__=="__main__":
    unittest.main()

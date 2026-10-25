import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime,timedelta,timezone
from pathlib import Path
from agent_forward_observer import observe_once

class ForwardObserverTests(unittest.TestCase):
    def test_bounded_progress_and_idempotent_replay(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            folder=root/"agent-forward";folder.mkdir()
            start=datetime(2026,10,26,tzinfo=timezone.utc)
            enrollment={"schema":"agent-forward-enrollment-v1","symbol":"BTCUSDT",
                        "strategy":"trend_8_30","research_sha256":"abc123",
                        "data_cutoff_utc":"2026-10-24T00:00:00Z",
                        "enrolled_at_utc":"2026-10-25T00:00:00Z",
                        "live_trading_authorized":False}
            (folder/"one.json").write_text(json.dumps(enrollment),encoding="utf-8")
            with closing(sqlite3.connect(root/"research.sqlite3")) as db:
                db.execute("CREATE TABLE candles(symbol TEXT,interval TEXT,mode TEXT,time TEXT,close_time TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
                for i in range(5):
                    at=start+timedelta(hours=i)
                    db.execute("INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)",
                               ("BTCUSDT","1h","live",at.isoformat(),
                                (at+timedelta(minutes=59,seconds=59)).isoformat(),
                                100,110,90,105,5))
                db.commit()
            kwargs={"max_bars_each":2,"now":"2026-10-27T00:00:00Z"}
            a=observe_once(td,**kwargs)
            b=observe_once(td,**kwargs)
            c=observe_once(td,**kwargs)
            d=observe_once(td,**kwargs)
            self.assertEqual([x["observed"] for x in (a,b,c,d)],[2,2,1,0])
            files=list((root/"agent-forward-observations"/"abc123").glob("*.json"))
            self.assertEqual(len(files),5)
            self.assertFalse(a["live_trading_authorized"])

    def test_missing_source_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(observe_once(td)["observed"],0)

if __name__=="__main__":
    unittest.main()

"""End-to-end disposable SQLite -> forward observation -> paper dashboard tests."""
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from agent_forward_observations import record_candle
from agent_forward_pipeline import run_once

class ForwardEndToEndTests(unittest.TestCase):
    def test_closed_candles_flow_to_paper_dashboard_and_restart_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            folder=root/"agent-forward"
            folder.mkdir()
            enrollment={"schema":"agent-forward-enrollment-v1",
                "symbol":"BTCUSDT","strategy":"trend_8_30",
                "research_sha256":"integration123",
                "data_cutoff_utc":"2026-10-20T00:00:00Z",
                "enrolled_at_utc":"2026-10-25T00:00:00Z",
                "live_trading_authorized":False}
            (folder/"one.json").write_text(json.dumps(enrollment),encoding="utf-8")
            start=datetime(2026,10,26,tzinfo=timezone.utc)
            db=sqlite3.connect(root/"research.sqlite3")
            db.execute("CREATE TABLE candles(symbol TEXT, interval TEXT, mode TEXT, time TEXT, close_time TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
            recorded=root/"agent-forward-observations"/"integration123"
            for i in range(86):
                at=start+timedelta(hours=i)
                price=100+i*.25
                bar={"time":at.isoformat(),"close_time":(at+timedelta(minutes=59,seconds=59)).isoformat(),
                     "open":price,"high":price+2,"low":price-2,"close":price+.1,"volume":100}
                db.execute("INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)",
                    ("BTCUSDT","1h","live",bar["time"],bar["close_time"],
                     bar["open"],bar["high"],bar["low"],bar["close"],bar["volume"]))
                if i<84:
                    record_candle(enrollment,bar,recorded,
                                  observed_at=(at+timedelta(hours=1)).isoformat())
            db.commit()
            db.close()
            current="2026-11-01T00:00:00Z"
            first=run_once(td,now=current)
            self.assertEqual(first["status"],"completed")
            self.assertEqual(first["observed"]["observed"],2)
            self.assertEqual(first["dashboard"]["rows"][0]["前向交易筆數"],1)
            self.assertEqual(first["dashboard"]["rows"][0]["驗證狀態"],"事後讀取，非即時驗證")
            self.assertFalse(first["live_trading_authorized"])
            second=run_once(td,now=current)
            self.assertEqual(second["status"],"completed")
            self.assertEqual(second["observed"]["observed"],0)
            self.assertEqual(len(list(recorded.glob("*.json"))),86)

if __name__=="__main__":
    unittest.main()

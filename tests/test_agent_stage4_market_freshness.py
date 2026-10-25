import sqlite3
import tempfile
import unittest
from pathlib import Path
from agent_stage4_market_freshness import inspect_freshness
from agent_stage4_audit import audit

class StageFourMarketFreshnessTests(unittest.TestCase):
    def test_recent_local_bar_never_proves_exchange_connection(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with sqlite3.connect(root/"research.sqlite3") as db:
                db.execute("CREATE TABLE candles(interval TEXT,mode TEXT,close_time TEXT)")
                db.execute("INSERT INTO candles VALUES(?,?,?)",("1h","live","2026-10-26T09:59:59+00:00"))
            result=inspect_freshness(td,now="2026-10-26T10:30:00Z")
            self.assertTrue(result["local_candle_recent"])
            self.assertFalse(result["exchange_connection_verified"])
            stage=audit(td,now="2026-10-26T10:30:00Z")
            self.assertTrue(stage["checks"]["local_market_candle_recent"])
            self.assertFalse(stage["checks"]["exchange_data_freshness_verified"])

    def test_old_and_future_bars_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with sqlite3.connect(root/"research.sqlite3") as db:
                db.execute("CREATE TABLE candles(interval TEXT,mode TEXT,close_time TEXT)")
                db.execute("INSERT INTO candles VALUES(?,?,?)",("1h","live","2026-10-25T00:59:59+00:00"))
            stale=inspect_freshness(td,now="2026-10-26T10:30:00Z")
            self.assertEqual(stale["status"],"stale_local_candle")
            self.assertFalse(stale["local_candle_recent"])
            with sqlite3.connect(root/"research.sqlite3") as db:
                db.execute("UPDATE candles SET close_time=?",("2026-10-26T11:59:59+00:00",))
            future=inspect_freshness(td,now="2026-10-26T10:30:00Z")
            self.assertEqual(future["reason"],"future_or_unclosed_candle")
            self.assertFalse(future["local_candle_recent"])

if __name__=="__main__":
    unittest.main()

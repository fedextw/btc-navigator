import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from agent_stage4_market_freshness import inspect_freshness

class PerSymbolFreshnessTests(unittest.TestCase):
    def test_stale_symbol_not_hidden_by_recent_btc(self):
        with tempfile.TemporaryDirectory() as td:
            with closing(sqlite3.connect(Path(td)/"research.sqlite3")) as db:
                db.execute("CREATE TABLE candles(symbol TEXT,interval TEXT,mode TEXT,close_time TEXT)")
                db.executemany("INSERT INTO candles VALUES(?,?,?,?)",[
                    ("BTCUSDT","1h","live","2026-10-26T09:59:59+00:00"),
                    ("ETHUSDT","1h","live","2026-10-25T09:59:59+00:00")])
                db.commit()
            global_result=inspect_freshness(td,now="2026-10-26T10:30:00Z")
            self.assertTrue(global_result["local_candle_recent"])
            result=inspect_freshness(td,now="2026-10-26T10:30:00Z",
                                     symbols=["BTCUSDT","ETHUSDT","SOLUSDT"])
            self.assertFalse(result["local_candle_recent"])
            self.assertEqual(result["symbol_freshness"]["BTCUSDT"],"recent")
            self.assertEqual(result["symbol_freshness"]["ETHUSDT"],"stale")
            self.assertEqual(result["symbol_freshness"]["SOLUSDT"],"missing")
            self.assertFalse(result["exchange_connection_verified"])
    def test_rejects_bad_symbol_selection(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                inspect_freshness(td,symbols=["BTCUSDT","BTCUSDT"])
            with self.assertRaises(ValueError):
                inspect_freshness(td,symbols=["BTCUSDT; DROP"])
if __name__=="__main__":
    unittest.main()

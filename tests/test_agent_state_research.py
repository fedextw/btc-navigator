import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from agent_state_research import history_from_database, run_from_state


class StateResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "research.sqlite3"
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("CREATE TABLE candles(symbol TEXT,interval TEXT,mode TEXT,time TEXT,close_time TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
            initial = datetime(2026, 1, 1, tzinfo=timezone.utc)
            for i in range(360):
                dt = initial + timedelta(hours=i)
                price = 100 + i*.05
                db.execute("INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)",
                    ("BTCUSDT","1h","demo",dt.isoformat(),(dt+timedelta(hours=1)).isoformat(),
                     price,price+1,price-1,price+.1,10))
            db.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_read_only_and_report(self):
        result = run_from_state(self.root,"BTCUSDT","1h","demo")
        self.assertEqual(result["bars"],360)
        self.assertFalse(result["live_trading_authorized"])
        self.assertTrue(Path(result["report_path"]).exists())

    def test_missing_live_mode_fails_closed(self):
        with self.assertRaises(ValueError):
            history_from_database(self.db,"BTCUSDT","1h","live")

    def test_gap_detected(self):
        with closing(sqlite3.connect(self.db)) as db:
            deleted = db.execute("DELETE FROM candles WHERE symbol=? AND interval=? AND mode=? AND time=?",
                ("BTCUSDT", "1h", "demo", (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=100)).isoformat()))
            self.assertEqual(deleted.rowcount, 1, "測試用 K 線未被刪除：請確認使用最新程式")
            db.commit()
        with closing(sqlite3.connect(self.db)) as check_db:
            remaining = check_db.execute("SELECT COUNT(*) FROM candles WHERE symbol=? AND interval=? AND mode=?", ("BTCUSDT","1h","demo")).fetchone()[0]
        self.assertEqual(remaining, 359, "刪除後資料庫根數不正確")
        with self.assertRaises(ValueError):
            history_from_database(self.db,"BTCUSDT","1h","demo")

    def test_reject_bad_symbol(self):
        with self.assertRaises(ValueError):
            history_from_database(self.db,"INVALID;DELETE","1h","demo")


if __name__ == "__main__":
    unittest.main()

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from agent_data_readiness import summarize

class ReadinessTests(unittest.TestCase):
    def test_missing_database_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=summarize(tmp)
            self.assertFalse(report["database_exists"])
            self.assertEqual(report["observed_pairs"],0)

    def test_bounded_continuity_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"research.sqlite3"
            begin=datetime(2026,1,1,tzinfo=timezone.utc)
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("CREATE TABLE candles(symbol TEXT, interval TEXT, mode TEXT, time TEXT)")
                for symbol,count,gap in (("BTCUSDT",300,False),("ETHUSDT",300,True),("XRPUSDT",20,False)):
                    conn.executemany("INSERT INTO candles VALUES (?,?,?,?)",[
                        (symbol,"1h","live",(begin+timedelta(hours=i+(1 if gap and i>=150 else 0))).isoformat())
                        for i in range(count)])
                conn.commit()
            report=summarize(tmp,inspect_limit=2)
            self.assertEqual(report["observed_pairs"],3)
            self.assertEqual(report["enough_bars"],2)
            self.assertEqual(report["checked_pairs"],2)
            self.assertEqual(report["ready_in_checked"],1)
            self.assertEqual(report["ready_examples"],["BTCUSDT"])

if __name__=="__main__":
    unittest.main()

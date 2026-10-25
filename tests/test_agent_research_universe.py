import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from agent_research_universe import next_batch

class RotatingUniverseTests(unittest.TestCase):
    def test_empty_database_waits(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(next_batch(td),())

    def test_rotates_only_ready_usdt_pairs(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"research.sqlite3"
            with closing(sqlite3.connect(p)) as db:
                db.execute("CREATE TABLE candles(symbol TEXT,interval TEXT,mode TEXT,time TEXT)")
                for symbol,count in (("BTCUSDT",301),("ETHUSDT",300),("SOLUSDT",400),("XRPUSDT",299),("DOGEBTC",350)):
                    db.executemany("INSERT INTO candles VALUES(?,?,?,?)",[(symbol,"1h","live",str(i)) for i in range(count)])
                db.commit()
            self.assertEqual(next_batch(td,limit=2,batch_number=0),("BTCUSDT","ETHUSDT"))
            self.assertEqual(next_batch(td,limit=2,batch_number=1),("SOLUSDT","BTCUSDT"))
            self.assertEqual(next_batch(td,limit=2,batch_number=2),("ETHUSDT","SOLUSDT"))

if __name__=="__main__":
    unittest.main()

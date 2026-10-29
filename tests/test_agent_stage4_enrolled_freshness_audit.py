import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from agent_stage4_audit import audit

class EnrolledFreshnessAuditTests(unittest.TestCase):
    def test_enrolled_stale_market_blocks_local_freshness(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            folder=root/"agent-forward";folder.mkdir()
            for symbol in ("BTCUSDT","ETHUSDT"):
                (folder/(symbol+".json")).write_text(json.dumps({
                    "schema":"agent-forward-enrollment-v1","symbol":symbol,
                    "live_trading_authorized":False
                }),encoding="utf-8")
            with closing(sqlite3.connect(root/"research.sqlite3")) as db:
                db.execute("CREATE TABLE candles(symbol TEXT, interval TEXT, mode TEXT, close_time TEXT)")
                db.executemany("INSERT INTO candles VALUES(?,?,?,?)",[
                    ("BTCUSDT","1h","live","2026-10-26T09:59:59+00:00"),
                    ("ETHUSDT","1h","live","2026-10-25T09:59:59+00:00")])
                db.commit()
            result=audit(td,now="2026-10-26T10:30:00Z")
            self.assertFalse(result["checks"]["local_market_candle_recent"])
            self.assertEqual(result["market_freshness_status"],"selected_symbols_not_all_recent")
            self.assertEqual(result["market_checked_symbols"],2)
            self.assertFalse(result["checks"]["exchange_data_freshness_verified"])

    def test_no_enrollments_cannot_certify_selected_market(self):
        with tempfile.TemporaryDirectory() as td:
            result=audit(td,now="2026-10-26T10:30:00Z")
            self.assertFalse(result["checks"]["local_market_candle_recent"])
            self.assertEqual(result["market_checked_symbols"],0)

if __name__=="__main__":
    unittest.main()

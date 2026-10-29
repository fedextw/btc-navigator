import json
import tempfile
import unittest
from pathlib import Path
from agent_forward_pipeline import run_once

class PartialObservationFailureTests(unittest.TestCase):
    def test_bad_enrollment_blocks_full_success_and_profit_claims(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            folder=root/"agent-forward"
            folder.mkdir()
            (folder/"bad.json").write_text(json.dumps({
                "schema":"agent-forward-enrollment-v1",
                "live_trading_authorized":False,
                "symbol":"BTCUSDT","strategy":"trend_8_30",
                "research_sha256":"abc123",
                "data_cutoff_utc":"not-a-date",
                "enrolled_at_utc":"2026-10-25T00:00:00Z"
            }),encoding="utf-8")
            import sqlite3
            db=sqlite3.connect(root/"research.sqlite3")
            db.execute("CREATE TABLE candles (symbol TEXT, interval TEXT, mode TEXT, time TEXT, close_time TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
            db.commit()
            db.close()
            result=run_once(td,now="2026-10-25T12:00:00Z")
            self.assertEqual(result["observed"]["skipped"],1)
            self.assertEqual(result["status"],"blocked_observer_errors")
            self.assertIsNone(result["dashboard"])
            self.assertFalse(result["live_trading_authorized"])
if __name__=="__main__":
    unittest.main()

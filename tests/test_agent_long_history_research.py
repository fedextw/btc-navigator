"""Regression: expanded historical dataset reaches the existing paper research engine."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from agent_state_research import history_from_database, run_from_state

class LongHistoryResearchTests(unittest.TestCase):
    def test_8760_utc_hourly_bars_available_to_research(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            dbpath=root/"research.sqlite3"
            with closing(sqlite3.connect(dbpath)) as db:
                db.execute("CREATE TABLE candles (symbol TEXT, interval TEXT, mode TEXT, time TEXT, close_time TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
                start=datetime(2025,1,1,tzinfo=timezone.utc)
                rows=[]
                for i in range(8760):
                    t=start+timedelta(hours=i)
                    rows.append(("BTCUSDT","1h","live",t.isoformat(),
                                 (t+timedelta(hours=1)-timedelta(milliseconds=1)).isoformat(),
                                 100.,105.,95.,101.,20.))
                db.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?)",rows)
                db.commit()
            bars=history_from_database(dbpath,"BTCUSDT","1h","live")
            self.assertEqual(len(bars),8760)
            sample={"selected":None,"paper_status":"rejected","reason":"test",
                    "profitability_evidence":{"eligible":False},"heldout":None}
            with patch("agent_state_research.run_cycle",return_value=sample) as runner:
                report=run_from_state(root,"BTCUSDT","1h","live")
            self.assertEqual(report["bars"],8760)
            runner.assert_called_once()

if __name__=="__main__":
    unittest.main()

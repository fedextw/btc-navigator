import tempfile
import unittest
from agent_research_scheduler import run_once
from agent_research_panel import load_status
from agent_research_scheduler import write_status

class BackfillReportingTests(unittest.TestCase):
    def test_success_records_insert_count_and_renders(self):
        attempts={}
        def researcher(_, symbol, interval, mode):
            attempts[symbol]=attempts.get(symbol,0)+1
            if attempts[symbol]==1: raise ValueError("累積 K 線不足 300 根")
            return {"selected":"none","status":"paper"}
        with tempfile.TemporaryDirectory() as td:
            report=run_once(td,runner=researcher,backfill_runner=lambda *a:{"status":"completed","inserted":300})
            self.assertEqual(report["items"][0]["backfill"]["inserted"],300)
            write_status(td,{**report,"phase":"completed"})
            parsed=load_status(td)
            self.assertEqual(parsed["items"][0]["backfill"],"補資料完成")
            self.assertEqual(parsed["items"][0]["backfill_inserted"],300)

    def test_failed_backfill_is_not_success(self):
        def missing(*args): raise FileNotFoundError("missing")
        def failed(*args): raise OSError("offline")
        with tempfile.TemporaryDirectory() as td:
            report=run_once(td,runner=missing,backfill_runner=failed)
        self.assertEqual(report["items"][0]["backfill"]["status"],"failed")
        self.assertEqual(report["items"][0]["backfill"]["error_type"],"OSError")
        self.assertFalse(report["live_trading_authorized"])

if __name__=="__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from agent_research_scheduler import run_once, write_status, main
from unittest.mock import patch
import json


class SchedulerTests(unittest.TestCase):
    def test_paper_comparison_exception_does_not_erase_scheduler_result(self):
        with tempfile.TemporaryDirectory() as directory:
            argv=["scheduler","--state-dir",directory,"--auto-universe","--once"]
            safe={"schema":"bc-forward-paper-batch-v1","items":[],
                  "live_trading_authorized":False}
            with patch("sys.argv",argv), \
                 patch("agent_research_universe.next_batch",return_value=()), \
                 patch("agent_forward_batch.review_frozen_batch",return_value=safe), \
                 patch("agent_fair_paper_queue.review_comparison_requests",
                       side_effect=ValueError("corrupted queue")):
                self.assertIsNone(main())
            status=json.loads((Path(directory)/"agent-status"/"latest.json").read_text())
            self.assertEqual(status["phase"],"completed")
            self.assertTrue(status["data_waiting"])
            self.assertEqual(status["fair_paper_comparisons"]["status"],"review_error")
            self.assertFalse(status["live_trading_authorized"])

    def test_two_scheduler_starts_preserve_paper_requests_and_cursor(self):
        from agent_fair_paper_queue import save_comparison_request
        from agent_research_cursor import save_cursor, read_cursor
        with tempfile.TemporaryDirectory() as directory:
            request={"status":"awaiting_fresh_independent_comparison",
                     "old_strategy":"trend_8_30","new_candidate":"breakout_20",
                     "old_historical_cutoff_utc":"2026-01-01T00:00:00+00:00",
                     "new_research_cutoff_utc":"2026-02-01T00:00:00+00:00",
                     "live_trading_authorized":False}
            save_comparison_request(directory,"BTCUSDT","1h",request)
            save_cursor(directory,7)
            stored=Path(directory)/"agent-paper-comparison-requests"
            originals={p.name:p.read_bytes() for p in stored.glob("*.json")}
            argv=["scheduler","--state-dir",directory,"--auto-universe","--once"]
            with patch("sys.argv",argv), \
                 patch("agent_research_universe.next_batch",return_value=()), \
                 patch("agent_fair_forward_comparison.compare_fresh_paper",
                       return_value={"status":"waiting_fresh_candles",
                                     "live_trading_authorized":False}):
                for _ in range(2):
                    self.assertIsNone(main())
                    report=json.loads((Path(directory)/"agent-status"/"latest.json").read_text())
                    self.assertEqual(report["phase"],"completed")
                    self.assertEqual(report["next_batch"],7)
                    self.assertEqual(report["fair_paper_comparisons"]["reviewed"],1)
                    self.assertFalse(report["live_trading_authorized"])
            self.assertEqual(read_cursor(directory),7)
            self.assertEqual(originals,
                             {p.name:p.read_bytes() for p in stored.glob("*.json")})

    def test_bounded_batch_and_paper_only(self):
        seen=[]
        def runner(root,symbol,interval,mode):
            seen.append(symbol)
            return {"bars":400}
        report=run_once(".",("BTCUSDT","ETHUSDT"),runner=runner)
        self.assertEqual(seen,["BTCUSDT","ETHUSDT"])
        self.assertTrue(report["paper_only"])
        self.assertFalse(report["live_trading_authorized"])

    def test_failure_isolated(self):
        def runner(root,symbol,interval,mode):
            if symbol=="BTCUSDT":raise ValueError("empty")
            return {"bars":500}
        report=run_once(".",("BTCUSDT","ETHUSDT"),runner=runner)
        self.assertEqual([i["status"] for i in report["items"]],["skipped","completed"])

    def test_rejects_unsafe_universe(self):
        for symbols in [(),("BTCUSDT",)*2,("BAD;DROP",),tuple(["BTCUSDT"]*11)]:
            with self.assertRaises(ValueError):run_once(".",symbols)

    def test_status_written_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            result=run_once(directory,("BTCUSDT",),runner=lambda *a: {"bars":300})
            path=write_status(directory,result)
            self.assertEqual(path,Path(directory)/"agent-status"/"latest.json")
            self.assertTrue(path.is_file())


if __name__=="__main__":unittest.main()

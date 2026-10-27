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

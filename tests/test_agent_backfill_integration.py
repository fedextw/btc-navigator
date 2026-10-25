import tempfile
import unittest
from agent_research_scheduler import run_once


class ResearchBackfillIntegrationTests(unittest.TestCase):
    def test_one_backfill_then_research(self):
        ready=set()
        called=[]
        def research(state,symbol,interval,mode):
            if symbol not in ready:
                raise ValueError("累積 K 線不足 300 根，停止研究")
            return {"status":"paper","selected":"none"}
        def backfill(state,symbol,interval):
            called.append(symbol)
            ready.add(symbol)
        with tempfile.TemporaryDirectory() as tmp:
            output=run_once(tmp,("BTCUSDT","ETHUSDT","SOLUSDT"),mode="live",
                            runner=research,backfill_runner=backfill,backfill_limit=2)
        self.assertEqual(called,["BTCUSDT","ETHUSDT"])
        self.assertEqual([x["status"] for x in output["items"]],
                         ["completed","completed","skipped"])
        self.assertEqual(output["items"][2]["error_type"],"DataNotReady")

    def test_demo_never_backfills(self):
        called=[]
        def runner(*args):
            raise FileNotFoundError()
        with tempfile.TemporaryDirectory() as tmp:
            output=run_once(tmp,mode="demo",runner=runner,
                            backfill_runner=lambda *args: called.append(args))
        self.assertEqual(called,[])
        self.assertEqual(output["items"][0]["error_type"],"DataNotReady")

    def test_backfill_error_is_isolated(self):
        def runner(*args):
            raise FileNotFoundError()
        def backfill(*args):
            raise OSError("unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            output=run_once(tmp,("BTCUSDT","ETHUSDT"),mode="live",
                            runner=runner,backfill_runner=backfill)
        self.assertEqual(len(output["items"]),2)
        self.assertEqual([x["status"] for x in output["items"]],["skipped","skipped"])
        self.assertFalse(output["live_trading_authorized"])

if __name__=="__main__":
    unittest.main()

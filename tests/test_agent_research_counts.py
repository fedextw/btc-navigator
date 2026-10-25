import tempfile
import unittest
from agent_research_scheduler import run_once, write_status
from agent_research_panel import load_status

class ResearchBatchCountsTests(unittest.TestCase):
    def test_batch_counts_are_actual_results(self):
        def research(root,symbol,interval,mode):
            if symbol=="ETHUSDT": raise FileNotFoundError()
            if symbol=="SOLUSDT": raise ValueError("bad parameters")
            return {"selected":"none","status":"paper"}
        with tempfile.TemporaryDirectory() as td:
            result=run_once(td,("BTCUSDT","ETHUSDT","SOLUSDT"),runner=research)
            self.assertEqual(result["counts"],{"attempted":3,"completed":1,"waiting":1,"skipped_other":1})
            write_status(td,{**result,"phase":"completed"})
            self.assertEqual(load_status(td)["counts"]["completed"],1)
            self.assertFalse(result["live_trading_authorized"])

if __name__=="__main__":
    unittest.main()

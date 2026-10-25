import tempfile
import unittest
from agent_stage5_cycle import run_research_review
from agent_stage5_batch import review_enrolled

class Stage5CycleTests(unittest.TestCase):
    def research(self,state_dir,*,symbols,interval,mode):
        self.assertEqual(interval,"1h")
        self.assertEqual(mode,"live")
        return {"schema":"agent-scheduler-v1","paper_only":True,
                "live_trading_authorized":False,"items":[],"counts":{"attempted":len(symbols)}}
    def test_integrated_research_and_real_empty_review(self):
        with tempfile.TemporaryDirectory() as td:
            result=run_research_review(td,symbols=["BTCUSDT"],research_runner=self.research,
                                       save=True,now="2026-10-26T10:00:00Z")
            self.assertEqual(result["schema"],"agent-stage5-cycle-v1")
            self.assertEqual(result["review"]["comparison"]["ranked"],[])
            self.assertFalse(result["automatic_promotion_authorized"])
            self.assertFalse(result["live_trading_authorized"])
            from pathlib import Path
            self.assertTrue(Path(result["review_snapshot"]).is_file())
    def test_unsafe_research_or_review_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            def unsafe(*args,**kwargs):
                return {"schema":"agent-scheduler-v1","paper_only":True,
                        "live_trading_authorized":True}
            with self.assertRaises(ValueError):
                run_research_review(td,symbols=["BTCUSDT"],research_runner=unsafe)
            def bad_review(*args,**kwargs):
                return {"schema":"agent-stage5-batch-v1",
                        "automatic_promotion_authorized":True,
                        "live_trading_authorized":False}
            with self.assertRaises(ValueError):
                run_research_review(td,symbols=["BTCUSDT"],research_runner=self.research,
                                    review_runner=bad_review)
if __name__=="__main__":
    unittest.main()

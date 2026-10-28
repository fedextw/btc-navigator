import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from agent_stage_four_supervisor import supervise
from agent_stage_four_ui_status import load_openai_status

class InterruptedResearchTests(unittest.TestCase):
    def test_ctrl_c_during_paid_research_requires_review(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            def interrupted(*args,**kwargs):
                calls.append(1)
                raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):
                supervise(Path(d)/"stage4-openai",max_batches=2,
                    runner=interrupted,
                    clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc))
            self.assertEqual(len(calls),1)
            self.assertEqual(load_openai_status(d)["state"],"requires_manual_review")
    def test_system_exit_during_paid_research_requires_review(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                supervise(Path(d)/"stage4-openai",max_batches=1,
                    runner=lambda *a,**kw: (_ for _ in ()).throw(SystemExit(1)),
                    clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc))
            self.assertEqual(load_openai_status(d)["state"],"requires_manual_review")

if __name__=="__main__":
    unittest.main()

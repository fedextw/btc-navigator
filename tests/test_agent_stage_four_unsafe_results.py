import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from agent_stage_four_supervisor import supervise
from agent_stage_four_ui_status import load_openai_status

class SupervisorUnsafeResultTests(unittest.TestCase):
    def test_unrecognized_rotation_status_halts_and_marks_error(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            def mock_rotation(*args,**kwargs):
                calls.append(1)
                return {"status":"unknown", "paper_only":True,
                        "live_trading_authorized":False}
            with self.assertRaisesRegex(ValueError,"Unsafe or unknown"):
                supervise(Path(d)/"stage4-openai",max_batches=2,
                          runner=mock_rotation,
                          clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc),
                          sleep=lambda seconds:None)
            self.assertEqual(len(calls),1)
            self.assertEqual(load_openai_status(d)["state"],"requires_manual_review")

    def test_live_trading_permission_never_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"Unsafe or unknown"):
                supervise(Path(d)/"stage4-openai",max_batches=1,
                          runner=lambda *a,**k:{"status":"completed",
                          "paper_only":False,"live_trading_authorized":True},
                          clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc))
            self.assertEqual(load_openai_status(d)["state"],"requires_manual_review")

if __name__=="__main__":
    unittest.main()

"""A failed remote research call may have been billed; require review."""
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone
from agent_stage_four_supervisor import supervise
from agent_stage_four_ui_status import load_openai_status

class UncertainBillingFailureTests(unittest.TestCase):
    def test_failed_runner_is_not_reported_as_safe_to_retry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            called=[]
            def raises(*args,**kwargs):
                called.append(True)
                raise ConnectionError("remote response lost after request")
            with self.assertRaises(ConnectionError):
                supervise(root/"stage4-openai",max_batches=1,runner=raises,
                    clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc))
            self.assertEqual(len(called),1)
            self.assertEqual(load_openai_status(root)["state"],"requires_manual_review")

if __name__=="__main__":
    unittest.main()

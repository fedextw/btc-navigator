import json
import os
import tempfile
import unittest
from pathlib import Path
from agent_forward_lock_diagnostic import inspect_lock

class ForwardLockDiagnosticTests(unittest.TestCase):
    def test_unlocked_or_recent_lock(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(inspect_lock(td)["state"],"unlocked")
            p=Path(td)/"agent-forward-pipeline.lock"
            p.write_text(json.dumps({"purpose":"paper_forward_pipeline","pid":12345}),encoding="utf-8")
            os.utime(p,(1000,1000))
            self.assertEqual(inspect_lock(td,now=1100)["state"],"locked_or_running")
            self.assertTrue(p.exists())
    def test_aged_lock_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"agent-forward-pipeline.lock"
            p.write_text(json.dumps({"purpose":"paper_forward_pipeline","pid":12345}),encoding="utf-8")
            os.utime(p,(1000,1000))
            outcome=inspect_lock(td,now=10000)
            self.assertEqual(outcome["state"],"requires_operator_review")
            self.assertTrue(p.exists())
            self.assertFalse(outcome["live_trading_authorized"])
    def test_corrupted_lock_requires_review(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"agent-forward-pipeline.lock"
            p.write_text("not json",encoding="utf-8")
            self.assertEqual(inspect_lock(td)["state"],"invalid_lock_requires_review")
            self.assertTrue(p.exists())

if __name__=="__main__":
    unittest.main()

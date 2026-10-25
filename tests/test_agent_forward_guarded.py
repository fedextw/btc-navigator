import tempfile
import unittest
from pathlib import Path
from agent_forward_guarded import guarded_run

class GuardedPipelineTests(unittest.TestCase):
    def test_guard_runs_once_and_cleans_lock(self):
        with tempfile.TemporaryDirectory() as td:
            outcome=guarded_run(td,now="2026-10-25T12:00:00Z")
            self.assertEqual(outcome["status"],"completed")
            self.assertFalse(outcome["live_trading_authorized"])
            self.assertFalse((Path(td)/"agent-forward-pipeline.lock").exists())

    def test_existing_lock_fails_closed_and_preserves_lock(self):
        with tempfile.TemporaryDirectory() as td:
            lock=Path(td)/"agent-forward-pipeline.lock"
            lock.write_text("existing",encoding="utf-8")
            outcome=guarded_run(td)
            self.assertEqual(outcome["status"],"already_running_or_stale_lock")
            self.assertEqual(lock.read_text(),"existing")
            self.assertFalse(outcome["live_trading_authorized"])

    def test_invalid_state_not_created(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"missing"
            with self.assertRaises(ValueError):
                guarded_run(path)
            self.assertFalse(path.exists())

if __name__=="__main__":
    unittest.main()

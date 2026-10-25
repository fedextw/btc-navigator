import tempfile
import unittest
from agent_forward_health import append_status
from agent_forward_continuity import summarize_continuity

class ContinuityTests(unittest.TestCase):
    def test_two_successful_runs_are_not_uptime_proof(self):
        with tempfile.TemporaryDirectory() as td:
            r={"status":"completed","cycles":[{}],"live_trading_authorized":False}
            append_status(td,r,stamp="2026-10-25T10:00:00Z")
            append_status(td,r,stamp="2026-10-25T11:00:00Z")
            result=summarize_continuity(td)
            self.assertEqual(result["status"],"recorded_history_only")
            self.assertEqual(result["records"],2)
            self.assertFalse(result["verified_uninterrupted_uptime"])
    def test_gap_and_failure_trigger_review(self):
        with tempfile.TemporaryDirectory() as td:
            append_status(td,{"status":"completed","cycles":[],"live_trading_authorized":False},stamp="2026-10-25T10:00:00Z")
            append_status(td,{"status":"stopped","cycles":[],"live_trading_authorized":False},stamp="2026-10-25T15:00:00Z")
            result=summarize_continuity(td,max_gap_seconds=7200)
            self.assertEqual(result["status"],"insufficient_or_interrupted")
            self.assertEqual(result["failed_records"],1)
            self.assertEqual(len(result["gaps"]),1)
if __name__=="__main__":
    unittest.main()

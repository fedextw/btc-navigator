import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from agent_forward_health import append_status
from agent_stage4_runtime_window import inspect_window
from agent_stage4_audit import audit

class RuntimeWindowTests(unittest.TestCase):
    def test_full_journal_coverage_is_not_uptime(self):
        with tempfile.TemporaryDirectory() as td:
            end=datetime(2026,10,26,tzinfo=timezone.utc)
            for hours_ago in range(72,-1,-2):
                stamp=(end-timedelta(hours=hours_ago)).isoformat()
                append_status(td,{"status":"completed","cycles":[{}],"live_trading_authorized":False},stamp=stamp)
            result=inspect_window(td,now=end.isoformat())
            self.assertTrue(result["journal_coverage_verified"])
            self.assertFalse(result["verified_uninterrupted_uptime"])
            acceptance=audit(td,now=end.isoformat())
            self.assertTrue(acceptance["checks"]["runtime_journal_72h_coverage"])
            self.assertFalse(acceptance["checks"]["long_duration_runtime_verified"])
    def test_missing_boundary_and_failed_cycle_do_not_pass(self):
        with tempfile.TemporaryDirectory() as td:
            end=datetime(2026,10,26,tzinfo=timezone.utc)
            append_status(td,{"status":"completed","cycles":[],"live_trading_authorized":False},
                          stamp=(end-timedelta(hours=10)).isoformat())
            append_status(td,{"status":"stopped","cycles":[],"live_trading_authorized":False},
                          stamp=end.isoformat())
            result=inspect_window(td,now=end.isoformat())
            self.assertFalse(result["journal_coverage_verified"])
            self.assertEqual(result["failed_records"],1)
if __name__=="__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from agent_stage4_audit import audit
from agent_forward_health import append_status

class StageFourAuditTests(unittest.TestCase):
    def test_empty_or_recent_health_never_auto_approves(self):
        with tempfile.TemporaryDirectory() as td:
            empty=audit(td,now="2026-10-26T00:00:00Z")
            self.assertEqual(empty["status"],"requires_more_evidence")
            self.assertFalse(empty["live_trading_authorized"])
            append_status(td,{"status":"completed","cycles":[],"live_trading_authorized":False},
                          stamp="2026-10-25T23:00:00Z")
            recent=audit(td,now="2026-10-26T00:00:00Z")
            self.assertTrue(recent["checks"]["periodic_health"])
            self.assertFalse(recent["checks"]["long_duration_runtime_verified"])
            self.assertEqual(recent["status"],"requires_more_evidence")

    def test_lock_blocks_acceptance(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td)/"agent-forward-pipeline.lock").write_text("invalid",encoding="utf-8")
            result=audit(td,now="2026-10-26T00:00:00Z")
            self.assertFalse(result["checks"]["lock_clear"])
            self.assertIn("lock_clear",result["failed_checks"])

if __name__=="__main__":
    unittest.main()

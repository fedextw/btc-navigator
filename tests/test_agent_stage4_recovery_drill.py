import tempfile
import unittest
from pathlib import Path
from agent_stage4_recovery_drill import run_drill
from agent_stage4_audit import audit

class LocalRecoveryDrillTests(unittest.TestCase):
    def test_isolated_drill_creates_evidence_without_touching_user_lock(self):
        with tempfile.TemporaryDirectory() as td:
            original=Path(td)/"agent-forward-pipeline.lock"
            original.write_text("keep-this-user-lock",encoding="utf-8")
            output=run_drill(td,stamp="2026-10-26T00:00:00Z")
            self.assertEqual(output["status"],"passed")
            self.assertEqual(original.read_text(encoding="utf-8"),"keep-this-user-lock")
            result=audit(td,now="2026-10-26T00:00:00Z")
            self.assertTrue(result["checks"]["isolated_local_recovery_drill_reported"])
            self.assertFalse(result["checks"]["recovery_drill_verified"])
            self.assertEqual(result["status"],"requires_more_evidence")
            with self.assertRaises(FileExistsError):
                run_drill(td,stamp="2026-10-26T00:00:00Z")
if __name__=="__main__":
    unittest.main()

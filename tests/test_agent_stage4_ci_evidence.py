import json
import tempfile
import unittest
from pathlib import Path
from agent_stage4_audit import audit

class StageFourCIEvidenceTests(unittest.TestCase):
    def test_ci_evidence_separate_from_real_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"agent-stage4-ci-evidence.json"
            file.write_text(json.dumps({"schema":"agent-stage4-ci-v1","windows":"success",
                          "linux":"success","run_url":"https://github.com/fedextw/btc-navigator/actions/runs/40212996936"}),encoding="utf-8")
            result=audit(td,now="2026-10-26T00:00:00Z")
            self.assertTrue(result["checks"]["recovery_ci_regression_reported"])
            self.assertFalse(result["checks"]["recovery_drill_verified"])
            self.assertFalse(result["checks"]["long_duration_runtime_verified"])
            self.assertEqual(result["status"],"requires_more_evidence")

    def test_invalid_ci_report_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"agent-stage4-ci-evidence.json"
            file.write_text(json.dumps({"schema":"agent-stage4-ci-v1","windows":"failure",
                          "linux":"success","run_url":"https://github.com/example/test"}),encoding="utf-8")
            self.assertFalse(audit(td)["checks"]["recovery_ci_regression_reported"])

if __name__=="__main__":
    unittest.main()

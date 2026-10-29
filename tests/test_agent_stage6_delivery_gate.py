import tempfile
import unittest
from unittest.mock import patch
from agent_stage6_delivery_gate import inspect_delivery

class Stage6DeliveryGateTests(unittest.TestCase):
    def test_empty_workspace_cannot_be_mistaken_for_deliverable_system(self):
        with tempfile.TemporaryDirectory() as td:
            report=inspect_delivery(td,now="2026-10-26T10:00:00Z")
            self.assertEqual(report["status"],"not_ready_for_delivery")
            self.assertIn("stage4_field_evidence_complete",report["blocking_checks"])
            self.assertIn("standalone_windows_package_verified",report["blocking_checks"])
            self.assertFalse(report["live_trading_authorized"])
    def test_favorable_paper_evidence_does_not_override_real_world_gates(self):
        stage4={"status":"ready_for_review","checks":{"runtime":True}}
        stage5={"schema":"agent-stage5-batch-v1","checked":1,
                "live_trading_authorized":False,"automatic_promotion_authorized":False,
                "candidates":[{"decision":{"status":"eligible_for_manual_paper_review"}}],
                "comparison":{"ranked":[{"rank":1}]}}
        with patch("agent_stage6_delivery_gate.audit",return_value=stage4),patch(
                "agent_stage6_delivery_gate.review_enrolled",return_value=stage5):
            report=inspect_delivery("/unused")
        self.assertTrue(report["checks"]["stage4_field_evidence_complete"])
        self.assertTrue(report["checks"]["strategy_candidates_reviewed"])
        self.assertEqual(report["status"],"not_ready_for_delivery")
        self.assertFalse(report["checks"]["actual_exchange_execution_verified"])
        self.assertFalse(report["checks"]["standalone_windows_package_verified"])
if __name__=="__main__":
    unittest.main()

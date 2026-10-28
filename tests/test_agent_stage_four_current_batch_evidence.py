import tempfile
import unittest
from unittest.mock import patch
from agent_stage_four_delivery import delivery

class StageFourCurrentBatchEvidenceTests(unittest.TestCase):
    def test_older_verified_audit_cannot_certify_new_waiting_or_review_batch(self):
        with tempfile.TemporaryDirectory() as td:
            for state in ("waiting_for_fresh_data","requires_manual_review","already_processed","empty_universe"):
                with self.subTest(state=state):
                    outcome={"status":state,"paper_only":True,"live_trading_authorized":False}
                    with patch("agent_stage_four_delivery.run_rotation",return_value=outcome),\
                         patch("agent_stage_four_delivery.audit_delivery",return_value={"engineering_evidence_valid":True}):
                        result=delivery(td,slot="20261029T00Z",execute=True,
                                        allow_model_calls=10,runner=lambda *a,**k:None)
                        self.assertFalse(result["engineering_evidence_valid"])
    def test_current_completed_batch_with_matching_audit_can_pass(self):
        with tempfile.TemporaryDirectory() as td:
            outcome={"status":"completed","paper_only":True,"live_trading_authorized":False}
            with patch("agent_stage_four_delivery.run_rotation",return_value=outcome),\
                 patch("agent_stage_four_delivery.audit_delivery",return_value={"engineering_evidence_valid":True}):
                result=delivery(td,slot="20261029T00Z",execute=True,
                                allow_model_calls=10,runner=lambda *a,**k:None)
                self.assertTrue(result["engineering_evidence_valid"])

if __name__=="__main__":
    unittest.main()

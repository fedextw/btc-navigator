import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_stage_four_delivery import delivery

class StageFourDeliveryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
    def test_read_only_preflight_no_model_or_binance_call(self):
        with patch("agent_stage_four_delivery.run_rotation") as run:
            result=delivery(self.root,slot="SLOT01")
        run.assert_not_called()
        self.assertEqual(result["mode"],"offline_preflight")
        self.assertFalse(result["engineering_evidence_valid"])
        self.assertFalse(result["live_trading_authorized"])
    def test_billed_execution_requires_explicit_maximum_acknowledgment(self):
        with patch("agent_stage_four_delivery.run_rotation") as run:
            with self.assertRaisesRegex(ValueError,"allow-model-calls"):
                delivery(self.root,slot="SLOT01",execute=True,allow_model_calls=1)
            run.assert_not_called()
    def test_real_execution_refuses_missing_api_key(self):
        with patch.dict("os.environ",{"OPENAI_API_KEY":""}),patch(
            "agent_stage_four_delivery.run_rotation") as run:
            with self.assertRaisesRegex(ValueError,"OPENAI_API_KEY"):
                delivery(self.root,slot="SLOT01",execute=True,allow_model_calls=10)
            run.assert_not_called()
    def test_explicit_runner_never_claims_forward_performance(self):
        with patch("agent_stage_four_delivery.run_rotation",
                   return_value={"status":"requires_manual_review",
                                 "paper_only":True,"live_trading_authorized":False}):
            result=delivery(self.root,slot="SLOT01",execute=True,
                            allow_model_calls=10,runner=lambda *a,**kw:None)
        self.assertFalse(result["real_forward_paper_validated"])
        self.assertFalse(result["profitability_proven"])
        self.assertFalse(result["live_trading_authorized"])
if __name__=="__main__":
    unittest.main()

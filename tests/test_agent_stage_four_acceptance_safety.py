import tempfile
import unittest
from unittest.mock import patch
from agent_stage_four_delivery import delivery

class StageFourAcceptanceSafetyTests(unittest.TestCase):
    def test_unsafe_rotation_cannot_be_certified(self):
        with tempfile.TemporaryDirectory() as td:
            for invalid in (
                {"status":"completed","paper_only":False,"live_trading_authorized":True},
                {"status":"completed"},
                {"status":"unknown","paper_only":True,"live_trading_authorized":False},
            ):
                with self.subTest(invalid=invalid):
                    with patch("agent_stage_four_delivery.run_rotation",return_value=invalid),\
                         patch("agent_stage_four_delivery.audit_delivery") as audit:
                        with self.assertRaisesRegex(ValueError,"Unsafe or unrecognized"):
                            delivery(td,slot="20261029T00Z",execute=True,allow_model_calls=10,runner=lambda *a,**k:None)
                        audit.assert_not_called()
if __name__=="__main__":
    unittest.main()

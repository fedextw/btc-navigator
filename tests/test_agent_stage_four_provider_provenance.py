import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import agent_stage_four_supervisor as module

class ProductionSafetyProvenanceTests(unittest.TestCase):
    def test_real_provider_missing_paper_only_attestation_halts(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            def real_runner(*args,**kwargs):
                calls.append(1)
                return {"status":"completed"}  # Missing explicit safety fields
            with patch.object(module,"run_rotation",real_runner):
                with self.assertRaisesRegex(ValueError,"Unsafe or unknown"):
                    module.supervise(Path(d)/"stage4-openai",max_batches=1,
                        runner=real_runner,
                        clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc))
            self.assertEqual(len(calls),1)
            from agent_stage_four_ui_status import load_openai_status
            self.assertEqual(load_openai_status(d)["state"],"requires_manual_review")
if __name__=="__main__":
    unittest.main()

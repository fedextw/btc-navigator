import json
import tempfile
import unittest
from pathlib import Path
from agent_stage_four_checkpoint import run_checkpointed

class StageFourRealFailureDiagnosticTests(unittest.TestCase):
    def test_failed_market_data_records_safe_diagnostic_and_never_retries(self):
        with tempfile.TemporaryDirectory() as td:
            calls=[]
            def bad_runner(out,previous,**kwargs):
                calls.append(1)
                raise ValueError("secret test token must not be persisted")
            with self.assertRaises(ValueError):
                run_checkpointed(td,None,slot="20261028T18Z",symbol="4USDT",runner=bad_runner)
            root=Path(td)
            checkpoint=json.loads((root/"stage4-checkpoint.json").read_text())
            diagnostic=json.loads((root/"failure-diagnostic.json").read_text())
            self.assertEqual(checkpoint["status"],"reserved")
            self.assertEqual(diagnostic["exception_type"],"ValueError")
            self.assertFalse(diagnostic["market_csv_saved"])
            self.assertEqual(diagnostic["model_charge_status"],"unknown")
            self.assertNotIn("secret",json.dumps(diagnostic))
            resumed=run_checkpointed(td,None,slot="20261028T18Z",symbol="4USDT",runner=bad_runner)
            self.assertEqual(resumed["status"],"requires_manual_review")
            self.assertEqual(calls,[1])
if __name__=="__main__":
    unittest.main()

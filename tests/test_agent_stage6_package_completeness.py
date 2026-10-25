import tempfile
import unittest
from pathlib import Path
from agent_release_preflight import ESSENTIAL, inspect

class StageSixPackageCompletenessTests(unittest.TestCase):
    def test_stage_five_and_six_modules_are_required_in_release(self):
        self.assertIn("agent_stage5_cycle.py", ESSENTIAL)
        self.assertIn("agent_stage5_batch.py", ESSENTIAL)
        self.assertIn("agent_stage6_delivery_gate.py", ESSENTIAL)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for name in ESSENTIAL:
                if name=="agent_stage6_delivery_gate.py":
                    continue
                (root/name).write_text("",encoding="utf-8")
            (root/"START_BC_RESEARCH_TEST.bat").write_text(
                'set "BTC_NAVIGATOR_STATE_DIR=%~dp0.agent-test-state"\n'
                'call START.bat --port 8591 --agent-research\n',encoding="utf-8")
            check=inspect(root)
            self.assertFalse(check["ready"])
            self.assertIn("agent_stage6_delivery_gate.py",check["missing_files"])

if __name__=="__main__":
    unittest.main()

"""Stage Four release gate must reject missing core AI research modules."""
import tempfile
import unittest
from pathlib import Path
from agent_release_preflight import ESSENTIAL, inspect

STAGE4 = (
    "agent_stage_four_supervisor.py",
    "agent_stage_four_rotation.py",
    "agent_stage_four_checkpoint.py",
    "agent_stage_four_integrated_audit.py",
    "agent_stage_four_ui_status.py",
    "agent_stage_four_readiness.py",
    "agent_stage_four_research.py",
)

class StageFourReleaseGateTests(unittest.TestCase):
    def test_all_stage_four_modules_are_release_essentials(self):
        for name in STAGE4:
            with self.subTest(name=name):
                self.assertIn(name, ESSENTIAL)

    def test_runtime_logs_secrets_and_state_never_enter_release(self):
        from agent_release_preflight import DANGEROUS
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ESSENTIAL:
                (root/name).write_text("",encoding="utf-8")
            (root/"START_BC_RESEARCH_TEST.bat").write_text(
                'set "BTC_NAVIGATOR_STATE_DIR=%~dp0.agent-test-state"\\n'
                'call "START.bat" --port 8591 --agent-research\\n',encoding="utf-8")
            for name in DANGEROUS:
                with self.subTest(path=name):
                    target=root/name
                    target.write_text("sensitive runtime content",encoding="utf-8")
                    self.assertFalse(inspect(root)["ready"])
                    self.assertIn(name,inspect(root)["runtime_or_secret_paths"])
                    target.unlink()

    def test_missing_one_stage_four_module_blocks_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ESSENTIAL:
                path=root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("",encoding="utf-8")
            (root/"START_BC_RESEARCH_TEST.bat").write_text(
                'set "BTC_NAVIGATOR_STATE_DIR=%~dp0.agent-test-state"\n'
                'call "START.bat" --port 8591 --agent-research\n',encoding="utf-8")
            baseline=inspect(root)
            self.assertTrue(baseline["ready"])
            for name in STAGE4:
                with self.subTest(name=name):
                    target=root/name
                    target.unlink()
                    result=inspect(root)
                    self.assertFalse(result["ready"])
                    self.assertIn(name,result["missing_files"])
                    target.write_text("",encoding="utf-8")

if __name__=="__main__":
    unittest.main()

import tempfile
from pathlib import Path
import unittest
from agent_release_preflight import ESSENTIAL, inspect


class ReleasePreflightTests(unittest.TestCase):
    def test_repository_has_complete_isolated_release_sources(self):
        root=Path(__file__).resolve().parents[1]
        result=inspect(root)
        self.assertTrue(result["ready"],result)

    def test_missing_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=inspect(tmp)
            self.assertFalse(result["ready"])
            self.assertIn("bootstrap.py",result["missing_files"])

    def test_secret_and_runtime_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ESSENTIAL:
                (root/name).write_text("",encoding="utf-8")
            (root/"START_BC_RESEARCH_TEST.bat").write_text(
                'set "BTC_NAVIGATOR_STATE_DIR=%~dp0.agent-test-state"\n'
                'call START.bat --port 8591 --agent-research\n',encoding="utf-8")
            self.assertTrue(inspect(root)["ready"])
            (root/".env").write_text("DO_NOT_PACKAGE=true",encoding="utf-8")
            report=inspect(root)
            self.assertFalse(report["ready"])
            self.assertIn(".env",report["runtime_or_secret_paths"])


if __name__=="__main__":
    unittest.main()

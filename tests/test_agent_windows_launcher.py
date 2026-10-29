"""Static safety regression for the independent Windows launcher."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IndependentLaunchTests(unittest.TestCase):
    def test_windows_research_launcher_isolated(self):
        text = (ROOT / "START_BC_RESEARCH_TEST.bat").read_text(encoding="utf-8")
        self.assertIn('set "BTC_NAVIGATOR_STATE_DIR=%~dp0.agent-test-state"', text)
        self.assertIn("--port 8591 --agent-research", text)
        self.assertIn('call "%~dp0START.bat"', text)
        self.assertNotIn("--live-trading", text)
        self.assertNotIn("--demo-test-stop", text)


if __name__ == "__main__":
    unittest.main()

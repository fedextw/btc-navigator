import unittest
from pathlib import Path

class WindowsOpenAIConsentTests(unittest.TestCase):
    def test_start_requires_active_key_and_explicit_choice(self):
        source=(Path(__file__).resolve().parents[1]/"START_BC_RESEARCH_TEST.bat").read_text(encoding="utf-8")
        self.assertIn("if defined OPENAI_API_KEY (",source)
        self.assertIn("choice /C 14N",source)
        self.assertIn('set "BC_OPENAI_ARGS=--openai-batches 1 --openai-ack-calls 10"',source)
        self.assertIn('set "BC_OPENAI_ARGS=--openai-batches 4 --openai-ack-calls 40"',source)
        self.assertIn('set "BC_OPENAI_ARGS="',source)
        self.assertIn("if errorlevel 3 (",source)
        self.assertIn('call "%~dp0START.bat" --port 8591 --agent-research %BC_OPENAI_ARGS%',source)
if __name__=="__main__":
    unittest.main()

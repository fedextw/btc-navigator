"""Contract check for single START -> paid-consent -> supervisor -> UI path.

Static wiring checks complement the real stateful test in release_acceptance.
No API key, external network, or billing during CI.
"""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class StageFourStartupWiringTests(unittest.TestCase):
    def test_windows_consent_goes_through_launcher_to_supervisor_and_ui(self):
        bat=(ROOT/"START_BC_RESEARCH_TEST.bat").read_text(encoding="utf-8")
        launch=(ROOT/"launch.py").read_text(encoding="utf-8")
        supervisor=(ROOT/"agent_stage_four_supervisor.py").read_text(encoding="utf-8")
        panel=(ROOT/"agent_research_panel.py").read_text(encoding="utf-8")
        reader=(ROOT/"agent_stage_four_ui_status.py").read_text(encoding="utf-8")
        self.assertIn("choice /C 14N",bat)
        self.assertIn("--openai-batches 1 --openai-ack-calls 10",bat)
        self.assertIn("--openai-batches 4 --openai-ack-calls 40",bat)
        self.assertIn("--agent-research %BC_OPENAI_ARGS%",bat)
        self.assertIn('args.openai_ack_calls != 10 * args.openai_batches',launch)
        self.assertIn('agent_stage_four_supervisor.py',launch)
        self.assertIn('state / "stage4-openai"',launch)
        self.assertIn('state / "openai-stage4.log"',launch)
        self.assertIn('supervisor-status.json',supervisor)
        self.assertIn('from agent_stage_four_ui_status import load_openai_status',panel)
        self.assertIn('stage4-openai',reader)
        self.assertIn('not_started',reader)
    def test_ai_research_panel_displays_verified_evidence_not_fake_performance(self):
        panel=(ROOT/"agent_research_panel.py").read_text(encoding="utf-8")
        self.assertIn('audit_delivery(Path(state_root)/"stage4-openai")',panel)
        self.assertIn('evidence["reports_verified"]',panel)
        self.assertIn('evidence["engineering_evidence_valid"]',panel)
        self.assertIn("研究證據完整不等於前向模擬獲利",panel)
    def test_default_windows_start_never_enables_unapproved_paid_calls(self):
        bat=(ROOT/"START_BC_RESEARCH_TEST.bat").read_text(encoding="utf-8")
        launch=(ROOT/"launch.py").read_text(encoding="utf-8")
        self.assertIn('set "BC_OPENAI_ARGS="',bat)
        self.assertIn('if errorlevel 3 (',bat)
        self.assertIn('if defined OPENAI_API_KEY (',bat)
        self.assertIn('default=0, help="明確授權 B+C OpenAI',launch)
        self.assertIn('if args.openai_batches:',launch)

if __name__=="__main__":
    unittest.main()

"""Launcher integration regression checks. Does NOT spawn live network processes."""
import ast
import unittest
from pathlib import Path


class LaunchAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).resolve().parents[1] / "launch.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_opt_in_switch_is_present(self):
        self.assertIn('"--agent-research"', self.source)
        self.assertIn('if args.agent_research:', self.source)

    def test_agent_is_separate_and_stopped(self):
        self.assertIn('"agent_research_scheduler.py"', self.source)
        self.assertIn('agent = subprocess.Popen(', self.source)
        self.assertIn('stop(agent)', self.source)

    def test_scanner_still_starts_without_agent(self):
        self.assertIn('worker = subprocess.Popen(', self.source)
        self.assertIn('if worker.poll() is not None:', self.source)
        self.assertIn('if args.agent_research:', self.source)

    def test_dedicated_log_and_paper_only(self):
        self.assertIn('"agent-research.log"', self.source)
        self.assertIn('"--hours", "6" if not args.demo else "24"', self.source)


if __name__ == "__main__":
    unittest.main()

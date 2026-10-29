import ast
import unittest
from pathlib import Path


class AgentRecoveryTests(unittest.TestCase):
    def test_launcher_recovery_is_bounded(self):
        source = (Path(__file__).resolve().parents[1] / "launch.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("agent_restart_count < 2", source)
        self.assertIn("agent_next_restart = time.monotonic() + 60", source)
        self.assertIn("stop(agent)", source)

    def test_scheduler_uses_os_lock(self):
        source = (Path(__file__).resolve().parents[1] / "agent_research_scheduler.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("with research_lock(args.state_dir):", source)
        self.assertIn("except AlreadyRunning as exc:", source)


if __name__ == "__main__":
    unittest.main()

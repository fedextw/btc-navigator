import unittest
from pathlib import Path


class DashboardIntegrationTests(unittest.TestCase):
    def test_research_sidebar_is_wired(self):
        dashboard = (Path(__file__).resolve().parents[1] / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn('"AI Agent 研究中心"', dashboard)
        self.assertIn('render_agent_research(STATE_ROOT)', dashboard)

    def test_frontend_and_scanner_remain_unmodified_routes(self):
        dashboard = (Path(__file__).resolve().parents[1] / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn('if portal==\'交易前台\':', dashboard)
        self.assertIn('frontend(page)', dashboard)
        self.assertIn('scanner_page()', dashboard)


if __name__ == "__main__":
    unittest.main()

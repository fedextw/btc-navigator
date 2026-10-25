import unittest
from agent_research_scheduler import run_once


class SchedulerProposalIntegrationTests(unittest.TestCase):
    def test_opt_in_calls_both_research_pipelines(self):
        calls = []
        def primary(state, symbol, interval, mode):
            calls.append("primary")
            return {"selected": None, "status": "rejected"}
        def proposed(state, symbol, interval, mode):
            calls.append("proposal")
            return {"selected": None, "status": "no_qualified_candidate",
                    "live_trading_authorized": False}
        result = run_once("unused", ("BTCUSDT",), runner=primary, proposal_runner=proposed)
        self.assertEqual(calls, ["primary", "proposal"])
        self.assertFalse(result["live_trading_authorized"])
        self.assertIn("proposal_research", result["items"][0]["result"])

    def test_missing_proposal_does_not_break_main_research(self):
        def primary(*args):
            return {"selected": None, "status": "rejected"}
        def failed(*args):
            raise OSError("data not ready")
        result = run_once("unused", ("BTCUSDT",), runner=primary, proposal_runner=failed)
        item = result["items"][0]
        self.assertEqual(item["status"], "completed")
        self.assertEqual(item["result"]["proposal_research"]["status"], "skipped")
        self.assertFalse(item["result"]["proposal_research"]["live_trading_authorized"])

    def test_disabled_is_backward_compatible(self):
        def primary(*args):
            return {"status": "rejected"}
        result = run_once("unused", ("BTCUSDT",), runner=primary)
        self.assertNotIn("proposal_research", result["items"][0]["result"])


if __name__ == "__main__":
    unittest.main()

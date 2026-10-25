import json
import tempfile
import unittest
from pathlib import Path
from agent_research_panel import load_status
from agent_research_scheduler import run_once, write_status


class SchedulerHealthTests(unittest.TestCase):
    def test_completed_batch_records_timestamp(self):
        report = run_once(".", ("BTCUSDT",), runner=lambda *args: {"bars": 400})
        self.assertTrue(report["finished_at"].endswith("+00:00"))
        self.assertFalse(report["live_trading_authorized"])

    def test_running_phase_is_visible(self):
        with tempfile.TemporaryDirectory() as root:
            write_status(root, {"schema": "agent-scheduler-v1", "phase": "running",
                                "started_at": "2026-10-25T13:00:00+00:00",
                                "paper_only": True, "live_trading_authorized": False, "items":[]})
            record = load_status(root)
            self.assertEqual(record["state"], "running")
            self.assertIn("正在執行",record["message"])

    def test_error_phase_is_visible(self):
        with tempfile.TemporaryDirectory() as root:
            write_status(root, {"schema":"agent-scheduler-v1", "phase":"error",
                                "paper_only":True, "live_trading_authorized":False,
                                "error_type":"OSError","items":[]})
            record = load_status(root)
            self.assertEqual(record["state"],"error")

    def test_unrecognized_phase_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            write_status(root, {"schema":"agent-scheduler-v1", "phase":"approved_live",
                                "paper_only":True, "live_trading_authorized":False,"items":[]})
            self.assertEqual(load_status(root)["state"],"invalid")


if __name__ == "__main__":
    unittest.main()

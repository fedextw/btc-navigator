import json
import os
import tempfile
import unittest
from pathlib import Path
from agent_forward_health import append_status
from agent_forward_health_summary import inspect_forward_health

class ForwardHealthSummaryTests(unittest.TestCase):
    def test_no_records_is_not_started(self):
        with tempfile.TemporaryDirectory() as td:
            r=inspect_forward_health(td,now="2026-10-25T12:00:00Z")
            self.assertEqual(r["status"],"not_started")
            self.assertFalse(r["live_trading_authorized"])

    def test_completed_research_is_not_a_profit_claim(self):
        with tempfile.TemporaryDirectory() as td:
            append_status(td,{"status":"completed","cycles":[],"live_trading_authorized":False},
                          stamp="2026-10-25T11:00:00Z")
            r=inspect_forward_health(td,now="2026-10-25T12:00:00Z")
            self.assertEqual(r["status"],"recently_completed")
            self.assertIn("不能",r["message"])

    def test_corrupt_lock_requires_review_even_if_research_recent(self):
        with tempfile.TemporaryDirectory() as td:
            append_status(td,{"status":"completed","cycles":[],"live_trading_authorized":False},
                          stamp="2026-10-25T11:00:00Z")
            p=Path(td)/"agent-forward-pipeline.lock"
            p.write_text("broken",encoding="utf-8")
            r=inspect_forward_health(td,now="2026-10-25T12:00:00Z")
            self.assertEqual(r["status"],"requires_operator_review")
            self.assertTrue(p.exists())

if __name__=="__main__":
    unittest.main()

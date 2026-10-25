import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from agent_forward_pipeline import run_once

class PipelineTests(unittest.TestCase):
    def test_empty_state_never_claims_profit(self):
        with tempfile.TemporaryDirectory() as td:
            first=run_once(td,now="2026-10-25T12:00:00Z")
            self.assertEqual(first["status"],"completed")
            self.assertEqual(first["registered"]["registered"],0)
            self.assertEqual(first["observed"]["observed"],0)
            self.assertEqual(first["dashboard"]["rows"],[])
            self.assertFalse(first["live_trading_authorized"])

    def test_invalid_enrollment_reports_failure_without_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);folder=root/"agent-forward";folder.mkdir()
            (folder/"bad.json").write_text('{"live_trading_authorized":true}',encoding="utf-8")
            result=run_once(td,now="2026-10-25T12:00:00Z")
            self.assertEqual(result["status"],"completed")
            self.assertEqual(result["dashboard"]["rows"][0]["驗證狀態"],"資料異常，未計入")
            self.assertFalse(result["live_trading_authorized"])

    def test_missing_directory_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                run_once(Path(td)/"missing")

if __name__=="__main__":
    unittest.main()

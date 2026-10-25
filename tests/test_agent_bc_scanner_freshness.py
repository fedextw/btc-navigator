import os
import tempfile
import unittest
from pathlib import Path
from agent_bc_diagnostic import inspect

class ScannerFreshnessDiagnosticTests(unittest.TestCase):
    def test_recent_log_and_optional_missing_services(self):
        with tempfile.TemporaryDirectory() as td:
            log=Path(td)/"scanner.log"
            log.write_text("ok",encoding="utf-8")
            os.utime(log,(1000,1000))
            result=inspect(td,port=8591,now=1100)
            self.assertTrue(result["scanner_log_recent"])
            self.assertEqual(result["scanner_log_age_seconds"],100)
            self.assertIn("不能證明",result["scanner_log_note"])
    def test_stale_log_is_flagged_independently_of_website(self):
        with tempfile.TemporaryDirectory() as td:
            log=Path(td)/"scanner.log"
            log.write_text("old",encoding="utf-8")
            os.utime(log,(1000,1000))
            result=inspect(td,port=8591,now=2000)
            self.assertFalse(result["scanner_log_recent"])
            self.assertIn("超過3分鐘",result["recommendation"])
    def test_absent_log_is_unknown_not_proven_disconnect(self):
        with tempfile.TemporaryDirectory() as td:
            result=inspect(td,port=8591,now=2000)
            self.assertIsNone(result["scanner_log_age_seconds"])
            self.assertFalse(result["scanner_log_recent"])
if __name__=="__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from agent_research_pending import load_pending, save_pending, clear_pending
from agent_research_cursor import failed_symbols

class FailedResearchRetryTests(unittest.TestCase):
    def test_only_failed_contracts_retained_across_restart(self):
        with tempfile.TemporaryDirectory() as td:
            report={"items":[{"symbol":"BTCUSDT","status":"completed"},
                             {"symbol":"ETHUSDT","status":"skipped"},
                             {"symbol":"SOLUSDT","status":"completed"}]}
            failed=failed_symbols(report)
            self.assertEqual(failed,("ETHUSDT",))
            save_pending(td,3,failed)
            self.assertEqual(load_pending(td,3),("ETHUSDT",))
            with self.assertRaises(ValueError):
                load_pending(td,4)
            clear_pending(td)
            self.assertEqual(load_pending(td,3),())

    def test_broken_file_and_malicious_symbols_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                save_pending(td,0,("../secret",))
            path=Path(td)/"agent-research-pending.json"
            path.write_text('{"schema":"agent-research-pending-v1","batch_number":0,"symbols":["BTCUSDT"],"live_trading_authorized":true}',encoding="utf-8")
            with self.assertRaises(ValueError):
                load_pending(td,0)

if __name__=="__main__":
    unittest.main()

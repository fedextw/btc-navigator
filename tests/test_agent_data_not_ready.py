import tempfile
import unittest
from agent_research_scheduler import run_once

class DataNotReadyTests(unittest.TestCase):
    def test_missing_research_database_is_waiting_not_crash(self):
        def runner(*_):
            raise FileNotFoundError("not initialized")
        with tempfile.TemporaryDirectory() as folder:
            report=run_once(folder,symbols=("BTCUSDT",),runner=runner)
        self.assertEqual(report["items"][0]["status"],"skipped")
        self.assertEqual(report["items"][0]["error_type"],"DataNotReady")
        self.assertFalse(report["live_trading_authorized"])

    def test_insufficient_bars_is_waiting(self):
        def runner(*_):
            raise ValueError("累積 K 線不足 300 根，停止研究")
        with tempfile.TemporaryDirectory() as folder:
            report=run_once(folder,symbols=("ETHUSDT",),runner=runner)
        self.assertEqual(report["items"][0]["error_type"],"DataNotReady")

if __name__=="__main__":
    unittest.main()

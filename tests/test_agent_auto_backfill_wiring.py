"""B+C one-click public candle preparation wiring and research safety."""
from pathlib import Path
import tempfile
import unittest
from agent_research_scheduler import run_once

ROOT=Path(__file__).resolve().parents[1]

class AutomaticBackfillTests(unittest.TestCase):
    def test_isolated_launcher_enables_live_only_backfill(self):
        source=(ROOT/"launch.py").read_text(encoding="utf-8")
        self.assertIn('if not args.demo:',source)
        self.assertIn('agent_command.append("--backfill-missing")',source)
        self.assertIn('"--agent-research"',(ROOT/"START_BC_RESEARCH_TEST.bat").read_text(encoding="utf-8"))

    def test_one_cycle_backfills_then_checks_and_records_paper_research(self):
        called=[]
        def research(root,symbol,interval,mode):
            called.append("research")
            if called.count("research")==1:
                raise ValueError("累積 K 線不足 300 根，停止研究")
            return {"status":"paper_only","live_trading_authorized":False}
        def fill(root,symbol,interval):
            called.append("backfill")
            return {"status":"completed","inserted":300}
        with tempfile.TemporaryDirectory() as td:
            report=run_once(td,("BTCUSDT",),runner=research,backfill_runner=fill)
        self.assertEqual(called,["research","backfill","research"])
        self.assertEqual(report["counts"]["completed"],1)
        self.assertEqual(report["items"][0]["backfill"]["inserted"],300)
        self.assertFalse(report["live_trading_authorized"])

    def test_demo_never_fetches_real_candles(self):
        def missing(*args):
            raise ValueError("累積 K 線不足 300 根，停止研究")
        def forbidden(*args):
            self.fail("demo must not fetch exchange data")
        with tempfile.TemporaryDirectory() as td:
            report=run_once(td,("BTCUSDT",),mode="demo",runner=missing,backfill_runner=forbidden)
        self.assertEqual(report["counts"]["waiting"],1)
        self.assertFalse(report["live_trading_authorized"])

if __name__=="__main__":
    unittest.main()

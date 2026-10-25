"""Offline subprocess smoke test: real scheduler CLI, no network or orders."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
SCHEDULER = ROOT / "agent_research_scheduler.py"


def seed(root):
    database = root / "research.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE candles (symbol TEXT, interval TEXT, mode TEXT, time TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = []
        for i in range(360):
            p = 100 + i * .07
            rows.append(("BTCUSDT", "1h", "demo", (start + timedelta(hours=i)).isoformat(),
                         p, p+1, p-1, p+.1, 100))
        db.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?)", rows)
        db.commit()


class AgentSubprocessSmokeTests(unittest.TestCase):
    def test_real_scheduler_once_against_disposable_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed(root)
            proc = subprocess.run([sys.executable, str(SCHEDULER),
                                   "--state-dir", str(root), "--mode", "demo",
                                   "--once", "--proposal-research"],
                                  cwd=ROOT, capture_output=True, text=True, timeout=25)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            status_file = root / "agent-status" / "latest.json"
            self.assertTrue(status_file.is_file())
            record = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual(record["phase"], "completed")
            self.assertFalse(record["live_trading_authorized"])
            self.assertEqual(record["items"][0]["status"], "completed")
            self.assertIn("proposal_research", record["items"][0]["result"])
            self.assertTrue(list((root / "agent-cycles").glob("*.json")))
            self.assertTrue(list((root / "agent-proposals").glob("*.json")))

    def test_duplicate_instance_exits_with_code_2(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed(root)
            first = subprocess.Popen([sys.executable, str(SCHEDULER), "--state-dir", str(root),
                                      "--mode", "demo"],
                                     cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 12
                while not (root / "agent-status" / "latest.json").exists():
                    if first.poll() is not None:
                        self.fail("first scheduler quit unexpectedly")
                    if time.monotonic() > deadline:
                        self.fail("first scheduler did not start")
                    time.sleep(.1)
                second = subprocess.run([sys.executable, str(SCHEDULER), "--state-dir", str(root),
                                         "--mode", "demo", "--once"],
                                        cwd=ROOT, capture_output=True, text=True, timeout=10)
                self.assertEqual(second.returncode, 2, second.stdout + second.stderr)
            finally:
                first.terminate()
                try:
                    first.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    first.kill()
                    first.wait(timeout=6)


if __name__ == "__main__":
    unittest.main()

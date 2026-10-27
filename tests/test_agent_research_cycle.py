import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from agent_research_cycle import run_cycle, save_cycle


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / "sample.csv"
        with self.file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(("time", "open", "high", "low", "close", "volume"))
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            for i in range(500):
                p = 100 + i*.025 + (i%13)*.08
                writer.writerow(((start+timedelta(hours=i)).isoformat(), p, p+1, p-1, p+.04, 100))

    def tearDown(self):
        self.tmp.cleanup()

    def test_deterministic_repeat_and_paper_only(self):
        a, b = run_cycle(self.file), run_cycle(self.file)
        self.assertEqual(a, b)
        self.assertEqual(len(a["candidates"]), 16)
        self.assertFalse(a["live_trading_authorized"])

    def test_holdout_changed_does_not_change_selection(self):
        original = run_cycle(self.file)
        with self.file.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        for row in rows[401:]:
            for j in (1,2,3,4):
                row[j] = str(float(row[j]) + 1000)
        with self.file.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)
        changed = run_cycle(self.file)
        self.assertEqual(original["selected"], changed["selected"])
        self.assertEqual(original["candidates"], changed["candidates"])

    def test_append_only_report(self):
        result = run_cycle(self.file)
        output = Path(self.tmp.name) / "reports"
        self.assertEqual(save_cycle(result, output), save_cycle(result, output))
        self.assertEqual(len(list(output.glob("*.json"))), 1)

    def test_cost_fails_closed(self):
        with self.assertRaises(ValueError):
            run_cycle(self.file, cost=-1)


if __name__ == "__main__":
    unittest.main()

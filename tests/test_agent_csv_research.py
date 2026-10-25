import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_csv_research import research, read_candles, evaluate


class CSVResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "candles.csv"
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with self.path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time", "open", "high", "low", "close", "volume"])
            for i in range(360):
                p = 100 + 0.1*i + (i % 9)*0.01
                writer.writerow([(start+timedelta(hours=i)).isoformat(), p, p+1, p-1, p+0.1, 10])

    def tearDown(self):
        self.temp.cleanup()

    def test_reproducible_validation_and_heldout(self):
        a = research(self.path)
        b = research(self.path)
        self.assertEqual(a, b)
        self.assertEqual(a["candles"], 360)
        self.assertFalse(a["assessment"]["live_trading_authorized"])

    def test_future_holdout_not_used_to_choose(self):
        a = research(self.path)
        with self.path.open(encoding="utf-8", newline="") as source:
            rows = list(csv.reader(source))
        for row in rows[1+288:]:
            for j in (1,2,3,4):
                row[j] = str(float(row[j])+1000)
        with self.path.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)
        b = research(self.path)
        self.assertEqual(a["selected_strategy"], b["selected_strategy"])
        self.assertEqual(a["validation"], b["validation"])

    def test_reject_non_chronological(self):
        lines = self.path.read_text().splitlines()
        lines[4], lines[5] = lines[5], lines[4]
        self.path.write_text("\n".join(lines))
        with self.assertRaises(ValueError):
            read_candles(self.path)

    def test_no_fill_from_future_bars(self):
        bars, _ = read_candles(self.path)
        sides = [0]*len(bars)
        sides[200] = 1
        result = evaluate(bars, sides, 200, 203)
        self.assertEqual(result["trades"], 0)


if __name__ == "__main__":
    unittest.main()

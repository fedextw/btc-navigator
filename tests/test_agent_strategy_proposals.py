import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from agent_strategy_proposals import validate, study


class StrategyProposalTests(unittest.TestCase):
    def test_rejects_executable_payload(self):
        for spec in ({"family":"trend","lookback":10,"slow":50,"rationale":"test","code":"print(1)"},
                     {"family":"breakout","lookback":20,"slow":0,"rationale":"x","__class__":"X"}):
            with self.assertRaises(ValueError):
                validate(spec)

    def test_rejects_unsafe_parameters(self):
        for spec in ({"family":"trend","lookback":60,"slow":10,"rationale":"x"},
                     {"family":"breakout","lookback":20,"slow":10,"rationale":"x"},
                     {"family":"trend","lookback":True,"slow":50,"rationale":"x"}):
            with self.assertRaises(ValueError):
                validate(spec)

    def test_valid_spec_is_data_only(self):
        self.assertEqual(validate({"family":"trend","lookback":10,"slow":50,"rationale":"研究假設"})[1], "trend")

    def test_study_never_authorizes_live(self):
        with tempfile.TemporaryDirectory() as folder:
            csv_file = Path(folder)/"candles.csv"
            spec_file = Path(folder)/"proposal.json"
            spec_file.write_text(json.dumps({"family":"trend","lookback":10,"slow":50,"rationale":"test"}),encoding="utf-8")
            with csv_file.open("w",newline="",encoding="utf-8") as file:
                writer=csv.writer(file)
                writer.writerow(["time","open","high","low","close","volume"])
                start=datetime(2026,1,1,tzinfo=timezone.utc)
                for i in range(360):
                    p=100+i*.08
                    writer.writerow([(start+timedelta(hours=i)).isoformat(),p,p+1,p-1,p+.1,10])
            result=study(csv_file,spec_file)
            self.assertFalse(result["live_trading_authorized"])
            self.assertTrue(result["paper_only"])
            self.assertNotIn("heldout",result)


if __name__ == "__main__":
    unittest.main()

import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from agent_proposal_orchestrator import experiment, propose, save_report


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"prices.csv"
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        with self.path.open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f)
            w.writerow(("time","open","high","low","close","volume"))
            for i in range(400):
                p=100+i*.06+(i%7)*.01
                w.writerow(((start+timedelta(hours=i)).isoformat(),p,p+1,p-1,p+.04,100))

    def tearDown(self):
        self.temp.cleanup()

    def test_bounded_and_no_live_trading(self):
        report=experiment(self.path)
        self.assertLessEqual(report["candidate_count"],12)
        self.assertEqual(report["source"],"pre_registered_parameter_grammar")
        self.assertFalse(report["live_trading_authorized"])
        self.assertTrue(report["paper_only"])

    def test_holdout_change_cannot_change_validation(self):
        original=experiment(self.path)
        with self.path.open("r",newline="",encoding="utf-8") as f:
            rows=list(csv.reader(f))
        for row in rows[321:]:
            for index in (1,2,3,4):
                row[index]=str(float(row[index])+500)
        with self.path.open("w",newline="",encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        modified=experiment(self.path)
        self.assertEqual(original["candidates"],modified["candidates"])
        self.assertEqual(original["selected"],modified["selected"])

    def test_immutable_report(self):
        report=experiment(self.path)
        location=Path(self.temp.name)/"reports"
        self.assertEqual(save_report(report,location),save_report(report,location))
        self.assertEqual(len(list(location.glob("*.json"))),1)

    def test_only_pre_registered_specs(self):
        self.assertEqual(len(propose()),8)


if __name__=="__main__":
    unittest.main()

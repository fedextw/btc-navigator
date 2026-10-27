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


    def test_evolution_requires_new_dataset_and_keeps_lineage(self):
        prior=experiment(self.path)
        with self.assertRaises(ValueError):
            experiment(self.path, ancestor=prior)
        with self.path.open("a", encoding="utf-8") as stream:
            # Extend far enough that the new validation interval begins
            # strictly AFTER all candles available to the ancestor.
            origin=datetime(2026,1,1,tzinfo=timezone.utc)
            for i in range(400, 1000):
                p=100+i*.06+(i%7)*.01
                stream.write(f"{(origin+timedelta(hours=i)).isoformat()},{p},{p+1},{p-1},{p+.04},100\n")
        next_generation=experiment(self.path, ancestor=prior)
        self.assertEqual(next_generation["source"], "validation_guided_evolution")
        self.assertIsNotNone(next_generation["parent_report_sha256"])
        self.assertFalse(next_generation["live_trading_authorized"])
        self.assertLessEqual(next_generation["candidate_count"], 12)

    def test_reject_unsafe_ancestor_and_changed_cost(self):
        prior=experiment(self.path)
        unsafe=dict(prior, live_trading_authorized=True)
        with self.assertRaisesRegex(ValueError,"權限"):
            experiment(self.path,ancestor=unsafe)
        with self.assertRaisesRegex(ValueError,"成本"):
            experiment(self.path,cost=.002,ancestor=prior)
        malformed=dict(prior,candidate_count=999)
        with self.assertRaisesRegex(ValueError,"數量"):
            experiment(self.path,ancestor=malformed)

    def test_external_ai_specifications_are_bounded_and_auditable(self):
        proposal={"family":"trend","lookback":10,"slow":50,"rationale":"external hypothesis"}
        result=experiment(self.path, ai_proposals=[proposal])
        self.assertEqual(result["source"],"external_ai_specifications")
        self.assertEqual(result["candidate_count"],1)
        self.assertEqual(len(result["external_proposals_sha256"]),64)
        self.assertFalse(result["live_trading_authorized"])
        self.assertEqual(result, experiment(self.path, ai_proposals=[proposal]))

    def test_external_ai_proposals_reject_untrusted_strategy_code(self):
        bad={"family":"python_exec","lookback":10,"slow":50,"rationale":"unsafe"}
        with self.assertRaises(ValueError):
            experiment(self.path, ai_proposals=[bad])
        with self.assertRaises(ValueError):
            experiment(self.path, ai_proposals=[])
        with self.assertRaises(ValueError):
            experiment(self.path, ai_proposals=[{"family":"trend","lookback":10,"slow":50,"rationale":"ok"}],
                       ancestor=experiment(self.path))

    def test_evolution_rejects_untrusted_ancestor(self):
        with self.assertRaises(ValueError):
            experiment(self.path, ancestor={"schema":"unknown"})

if __name__=="__main__":
    unittest.main()

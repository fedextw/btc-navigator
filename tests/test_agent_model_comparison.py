import csv
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from agent_model_comparison import compare_models

class ModelComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.csv=self.root/"market.csv"
        origin=datetime(2025,1,1,tzinfo=timezone.utc)
        with self.csv.open("w",newline="",encoding="utf-8") as stream:
            writer=csv.writer(stream)
            writer.writerow(("time","open","high","low","close","volume"))
            for i in range(500):
                price=100+i*.03
                writer.writerow(((origin+timedelta(hours=i)).isoformat(),price,price+1,price-1,price,100))
    def test_comparison_freezes_dataset_cost_and_provider_isolation(self):
        calls=[]
        def provider(model,prompt):
            calls.append((model,prompt))
            spec={"family":"trend" if model=="small" else "mean_reversion",
                  "lookback":10,"slow":50 if model=="small" else 20,
                  "rationale":"research only"}
            return json.dumps([spec])
        result=compare_models(self.csv,self.root/"results",models=("small","large"),provider=provider)
        self.assertEqual([x["model"] for x in result["models"]],["small","large"])
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][1],calls[1][1])
        self.assertEqual(result["comparison_scope"],"same_dataset_validation_only")
        self.assertEqual(result["cost_fraction"],.0014)
        for entry in result["models"]:
            self.assertIn("best_validation_strategy",entry)
            self.assertIn("net_return_pct",entry["best_validation"])
            self.assertIn("profit_factor",entry["best_validation"])
            self.assertIn("max_drawdown_pct",entry["best_validation"])
        self.assertFalse(result["live_trading_authorized"])
        for entry in result["models"]:
            report=json.loads(Path(entry["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["dataset_sha256"],result["dataset_sha256"])
            self.assertFalse(report["live_trading_authorized"])
    def test_duplicate_model_rejected_before_invocation(self):
        used=[]
        with self.assertRaisesRegex(ValueError,"duplicate"):
            compare_models(self.csv,self.root/"bad",models=("same","same"),
                           provider=lambda *args:used.append(args))
        self.assertEqual(used,[])
    def test_existing_evidence_never_overwritten(self):
        folder=self.root/"existing"
        folder.mkdir()
        (folder/"existing.txt").write_text("saved",encoding="utf-8")
        with self.assertRaises(FileExistsError):
            compare_models(self.csv,folder,models=("one","two"),provider=lambda *_:"[]")
if __name__=="__main__":
    unittest.main()

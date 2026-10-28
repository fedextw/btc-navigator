import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_stage_three_delivery import run_delivery

class StageThreeDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def test_one_command_same_market_no_live_promotion(self):
        market=self.root/"market.csv"
        market.write_text("frozen",encoding="utf-8")
        trial={"market":{"csv":str(market),"dataset_sha256":"a"*64},
               "research":{"completed_generations":2,"reports":["prior-evidence.json"]},
               "provider_verified_by_live_calls":False,
               "acceptance":{"accepted":False}}
        comparison={"dataset_sha256":"a"*64,"models":[{"model":"baseline"},{"model":"challenger"}]}
        with patch("agent_stage_three_delivery.run_stage_three_trial",return_value=trial) as runner,patch(
            "agent_stage_three_delivery.compare_models",return_value=comparison) as matcher,patch(
            "agent_stage_three_delivery.resume_from_report",return_value={"report_path":"recovered.json"}):
            result=run_delivery(self.root/"delivery",comparison_models=("baseline","challenger"),
                                propose=lambda p:"[]",comparison_provider=lambda m,p:"[]")
        self.assertEqual(runner.call_count,1)
        self.assertEqual(matcher.call_count,1)
        self.assertEqual(matcher.call_args.args[0],str(market))
        self.assertEqual(result["comparison_models"],["baseline","challenger"])
        self.assertFalse(result["profitability_proven"])
        self.assertFalse(result["live_trading_authorized"])
        self.assertFalse(result["engineering_accepted"])
        self.assertFalse(result["comparison_provider_verified"])
        self.assertTrue((self.root/"delivery"/"delivery_summary.json").exists())
    def test_delivery_requires_comparison_provider_provenance(self):
        trial={"market":{"csv":"frozen.csv","dataset_sha256":"a"*64},
               "research":{"completed_generations":2,"reports":["prior-evidence.json"]},
               "provider_verified_by_live_calls":True,
               "acceptance":{"accepted":True}}
        comparison={"dataset_sha256":"a"*64,"models":[{"model":"one"},{"model":"two"}],
                    "real_provider_calls_verified":False}
        with patch("agent_stage_three_delivery.run_stage_three_trial",return_value=trial),patch(
            "agent_stage_three_delivery.compare_models",return_value=comparison),patch(
            "agent_stage_three_delivery.resume_from_report",return_value={"report_path":"recovered.json"}):
            report=run_delivery(self.root/"missing_model_proof")
        self.assertFalse(report["engineering_accepted"])
        self.assertFalse(report["comparison_provider_verified"])

    def test_resume_requires_independent_market_and_never_claims_live_provider_from_stub(self):
        trial={"market":{"csv":"frozen.csv","dataset_sha256":"a"*64},
               "research":{"completed_generations":2,"reports":["prior-evidence.json"]},
               "provider_verified_by_live_calls":True,
               "acceptance":{"accepted":True}}
        comparison={"dataset_sha256":"a"*64,"models":[{"model":"one"},{"model":"two"}],
                    "real_provider_calls_verified":True}
        resumed={"report_path":"resumed-evidence.json","live_trading_authorized":False}
        with patch("agent_stage_three_delivery.run_stage_three_trial",return_value=trial),patch(
            "agent_stage_three_delivery.compare_models",return_value=comparison),patch(
            "agent_stage_three_delivery.resume_from_report",return_value=resumed) as recovery:
            report=run_delivery(self.root/"recovered",resume_csv="new-market.csv",
                                resume_provider=lambda prompt:"[]")
        self.assertEqual(recovery.call_args.args[0],"new-market.csv")
        self.assertEqual(recovery.call_args.kwargs["previous_report_path"],"prior-evidence.json")
        self.assertFalse(report["research_resume_verified"])
        self.assertFalse(report["engineering_accepted"])
        self.assertEqual(report["research_resume_report"],"resumed-evidence.json")
    def test_mismatched_market_rejected(self):
        trial={"market":{"csv":"ignored","dataset_sha256":"a"*64},
               "research":{"completed_generations":2,"reports":["prior-evidence.json"]},
               "provider_verified_by_live_calls":True,
               "acceptance":{"accepted":True}}
        compare={"dataset_sha256":"b"*64,"models":[]}
        with patch("agent_stage_three_delivery.run_stage_three_trial",return_value=trial),patch(
            "agent_stage_three_delivery.compare_models",return_value=compare):
            with self.assertRaisesRegex(ValueError,"dataset differs"):
                run_delivery(self.root/"invalid")
        self.assertFalse((self.root/"invalid"/"delivery_summary.json").exists())
    def test_never_overwrites_existing_evidence(self):
        target=self.root/"existing"
        target.mkdir()
        (target/"keep.txt").write_text("never overwrite",encoding="utf-8")
        with self.assertRaises(FileExistsError):
            run_delivery(target)
if __name__=="__main__":
    unittest.main()

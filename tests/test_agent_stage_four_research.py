import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_stage_four_research import run_step

class StageFourResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.parent={"schema":"agent-orchestrator-v1","paper_only":True,
                     "live_trading_authorized":False}
        self.old=self.save(self.parent)
    def save(self,obj):
        raw=json.dumps(obj,sort_keys=True).encode()
        path=self.root/(hashlib.sha256(raw).hexdigest()+".json")
        path.write_bytes(raw)
        return path
    def test_new_market_bootstrap_creates_own_initial_report(self):
        report={"candidate_count":1,"candidates":[{"status":"rejected"}],
                "selected":None}
        saved=self.root/"bootstrap_report.json"
        saved.write_text(json.dumps(report),encoding="utf-8")
        with patch("agent_stage_four_research.download_public_candles",
                   return_value={"csv":"market.csv","candles":1600}) as download,patch(
            "agent_stage_four_research.model_research",
                   return_value={"report_path":str(saved)}) as first,patch(
            "agent_stage_four_research.resume_from_report") as resume:
            outcome=run_step(self.root/"newmarket",None,propose=lambda x:"[]")
        self.assertEqual(first.call_count,1)
        resume.assert_not_called()
        self.assertIsNone(outcome["parent_report_sha256"])
        self.assertEqual(outcome["generation"],"bootstrap")
        self.assertEqual(outcome["step_status"],"no_qualified_candidate")
        self.assertFalse(outcome["live_trading_authorized"])
    def test_reject_unhashed_parent_before_any_market_fetch(self):
        invalid=self.root/"prior.json"
        invalid.write_text("{}",encoding="utf-8")
        with patch("agent_stage_four_research.download_public_candles") as fetch:
            with self.assertRaisesRegex(ValueError,"content-address"):
                run_step(self.root/"bad",invalid)
            fetch.assert_not_called()
    def test_reject_existing_workspace_before_download(self):
        used=self.root/"used"
        used.mkdir()
        (used/"evidence").write_text("untouched",encoding="utf-8")
        with patch("agent_stage_four_research.download_public_candles") as fetch:
            with self.assertRaises(FileExistsError):
                run_step(used,self.old)
            fetch.assert_not_called()
    def test_bounded_step_records_failed_research_without_promotion(self):
        report={"candidate_count":1,"candidates":[{"status":"rejected"}],
                "selected":None}
        report_file=self.root/"mocked_report.json"
        report_file.write_text(json.dumps(report),encoding="utf-8")
        fake_market={"csv":"frozen.csv","dataset_sha256":"a"*64,
                     "candles":1600}
        fake_resume={"report_path":str(report_file),
                     "parent_report_sha256":"b"*64}
        with patch("agent_stage_four_research.download_public_candles",
                   return_value=fake_market) as fetch,patch(
            "agent_stage_four_research.resume_from_report",
                   return_value=fake_resume) as resume:
            result=run_step(self.root/"research",self.old,propose=lambda x:"[]")
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(resume.call_count,1)
        self.assertEqual(result["step_status"],"no_qualified_candidate")
        self.assertFalse(result["automatic_promotion"])
        self.assertFalse(result["live_trading_authorized"])
        self.assertEqual(result["model_provider_path"],"injected_test")
        self.assertTrue((self.root/"research"/"step_summary.json").exists())
if __name__=="__main__":
    unittest.main()

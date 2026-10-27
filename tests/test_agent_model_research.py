import csv
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from agent_model_research import model_research

class ModelResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.data=self.root/"candles.csv"
        origin=datetime(2026,1,1,tzinfo=timezone.utc)
        with self.data.open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f)
            w.writerow(("time","open","high","low","close","volume"))
            for i in range(400):
                p=100+i*.05
                w.writerow(((origin+timedelta(hours=i)).isoformat(),p,p+1,p-1,p,100))

    def test_model_proposal_enters_research_with_lineage(self):
        candidate={"family":"trend","lookback":10,"slow":50,"rationale":"model hypothesis"}
        result=model_research(self.data,self.root/"reports",lambda prompt:json.dumps([candidate]),model_id="test-stub")
        saved=json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["source"],"external_ai_specifications")
        self.assertEqual(saved["proposal_model_id"],"test-stub")
        self.assertEqual(len(saved["model_response_sha256"]),64)
        self.assertFalse(saved["live_trading_authorized"])
        self.assertEqual(saved["proposal_execution"],"bounded_data_only")

    def test_model_cannot_supply_executable_strategy(self):
        bad=[{"family":"python_exec","lookback":10,"slow":50,"rationale":"unsafe"}]
        with self.assertRaises(ValueError):
            model_research(self.data,self.root/"unsafe",lambda _:json.dumps(bad),model_id="test")
        self.assertFalse((self.root/"unsafe").exists())

    def test_dataset_change_during_model_call_rejects_evidence(self):
        from agent_csv_research import read_candles
        expected=read_candles(self.data)[1]
        candidate={"family":"trend","lookback":10,"slow":50,"rationale":"hypothesis"}
        def mutate_and_reply(_prompt):
            with self.data.open("a",encoding="utf-8") as file:
                file.write("2026-02-01T00:00:00+00:00,101,102,100,101,100\n")
            return json.dumps([candidate])
        with self.assertRaisesRegex(ValueError,"Dataset changed"):
            model_research(self.data,self.root/"rejected",mutate_and_reply,
                           model_id="test",expected_dataset_sha256=expected)
        self.assertFalse((self.root/"rejected").exists())

    def test_reject_oversized_and_malformed_responses(self):
        with self.assertRaises(ValueError):
            model_research(self.data,self.root/"huge",lambda _:"x"*16385,model_id="test")
        with self.assertRaises(ValueError):
            model_research(self.data,self.root/"bad",lambda _:"{}",model_id="test")
if __name__=="__main__":
    unittest.main()

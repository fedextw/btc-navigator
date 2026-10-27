import csv
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from agent_model_cycle import run_model_feedback_cycle

class ModelCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.data=self.root/"data.csv"
        origin=datetime(2026,1,1,tzinfo=timezone.utc)
        with self.data.open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f)
            w.writerow(("time","open","high","low","close","volume"))
            for i in range(1000):
                p=100+i*.1
                w.writerow(((origin+timedelta(hours=i)).isoformat(),p,p+1,p-1,p,100))
    def test_no_qualified_parent_stops_model_cycle(self):
        calls=[]
        def model(prompt):
            calls.append(prompt)
            return json.dumps([{"family":"trend","lookback":10,"slow":50,"rationale":"hypothesis"}])
        answer=run_model_feedback_cycle(self.data,self.root/"out",model,
                                         model_id="test-stub",first_cutoff=400,second_cutoff=1000)
        self.assertEqual(answer["completed_generations"],1)
        self.assertEqual(answer["stop_reason"],"no_qualified_parent")
        self.assertEqual(len(calls),1)
        self.assertFalse(answer["live_trading_authorized"])
    def test_unsafe_first_generation_report_is_rejected(self):
        model=lambda prompt:json.dumps([{"family":"trend","lookback":10,"slow":50,
                                         "rationale":"hypothesis"}])
        from agent_model_cycle import model_research as actual
        def tampered(*args,**kwargs):
            result=actual(*args,**kwargs)
            data=json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
            data["live_trading_authorized"]=True
            corrupted=self.root/"tampered.json"
            corrupted.write_text(json.dumps(data),encoding="utf-8")
            return dict(result,report_path=str(corrupted))
        with patch("agent_model_cycle.model_research",side_effect=tampered):
            with self.assertRaisesRegex(ValueError,"Unsafe"):
                run_model_feedback_cycle(self.data,self.root/"unsafe",model,
                    model_id="test-stub",first_cutoff=400,second_cutoff=1000)

    def test_overlap_rejected_before_model_call(self):
        calls=[]
        with self.assertRaisesRegex(ValueError,"overlaps"):
            run_model_feedback_cycle(self.data,self.root/"bad",lambda x:calls.append(x),
                                     model_id="test-stub",first_cutoff=400,second_cutoff=600)
        self.assertEqual(calls,[])
        self.assertFalse((self.root/"bad").exists())
    def test_second_generation_receives_feedback_when_qualified(self):
        calls=[]
        def model(prompt):
            calls.append(prompt)
            lookback=10 if len(calls)==1 else 13
            return json.dumps([{"family":"trend","lookback":lookback,"slow":50,
                                "rationale":"bounded hypothesis"}])
        from agent_model_cycle import model_research as actual_research
        # A test-only first-generation acceptance bypasses uncertain synthetic
        # profitability, while production still uses actual report selection.
        def first_mock(*args,**kwargs):
            result=actual_research(*args,**kwargs)
            path=Path(result["report_path"])
            data=json.loads(path.read_text(encoding="utf-8"))
            data["selected"]="fixture-qualified"
            fake=self.root/"qualified.json"
            fake.write_text(json.dumps(data),encoding="utf-8")
            result["report_path"]=str(fake)
            return result
        with patch("agent_model_cycle.model_research",side_effect=first_mock):
            answer=run_model_feedback_cycle(self.data,self.root/"out2",model,
                                             model_id="test-stub",first_cutoff=400,second_cutoff=1000)
        self.assertEqual(answer["completed_generations"],2)
        self.assertEqual(len(calls),2)
        later=json.loads(Path(answer["reports"][1]).read_text(encoding="utf-8"))
        self.assertTrue(later["model_feedback_used"])
        self.assertTrue(later["parent_report_sha256"])
if __name__=="__main__":
    unittest.main()

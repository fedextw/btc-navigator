import csv
import io
from contextlib import redirect_stdout
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from agent_model_cycle import run_model_feedback_cycle, run_multigeneration_model_cycle, resume_from_report, main

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
    def test_multigeneration_learns_from_unqualified_evidence(self):
        prompts=[]
        def model(prompt):
            prompts.append(prompt)
            return json.dumps([{"family":"trend","lookback":10+len(prompts), "slow":50,
                                "rationale":"paper hypothesis"}])
        result=run_multigeneration_model_cycle(self.data,self.root/"multi",model,
                         model_id="mocked",cutoffs=[400,1000])
        self.assertEqual(result["requested_generations"],2)
        self.assertEqual(result["completed_generations"],2)
        self.assertIsNone(result["stop_reason"])
        self.assertEqual(len(prompts),2)
        self.assertIn("validation_only_feedback",prompts[1])
        self.assertFalse(result["live_trading_authorized"])

    def test_multigeneration_preflight_rejects_overlap_before_model(self):
        prompts=[]
        with self.assertRaisesRegex(ValueError,"overlap"):
            run_multigeneration_model_cycle(self.data,self.root/"overlap",prompts.append,
                          model_id="mocked",cutoffs=[400,600])
        self.assertEqual(prompts,[])
        self.assertFalse((self.root/"overlap").exists())

    def test_multigeneration_cutoffs_are_bounded(self):
        with self.assertRaises(ValueError):
            run_multigeneration_model_cycle(self.data,self.root/"invalid",lambda _: "[]",
                model_id="mocked",cutoffs=[300,350,400,450,500])

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

    def test_cli_executes_cycle_without_real_model_credentials(self):
        spec={"family":"trend","lookback":10,"slow":50,"rationale":"research hypothesis"}
        argv=["cycle",str(self.data),"--out",str(self.root/"cli"),
              "--model","mocked-model","--first-cutoff","400","--second-cutoff","1000"]
        with patch("sys.argv",argv):
            with patch("agent_llm_adapter.openai_compatible_model",
                       return_value=json.dumps([spec])) as model:
                with redirect_stdout(io.StringIO()) as result:
                    main()
        payload=json.loads(result.getvalue())
        self.assertEqual(payload["completed_generations"],1)
        self.assertFalse(payload["live_trading_authorized"])
        self.assertEqual(model.call_count,1)

    def test_resume_rejected_parent_requires_fresh_validation_data(self):
        from agent_model_research import model_research
        model=lambda _:json.dumps([{"family":"trend","lookback":10,
                                     "slow":50,"rationale":"hypothesis"}])
        first=run_model_feedback_cycle(self.data,self.root/"first",model,
                                      model_id="stub",first_cutoff=400,second_cutoff=1000)
        prior=first["reports"][0]
        called=[]
        with self.assertRaisesRegex(ValueError,"Reused prior dataset|overlaps"):
            resume_from_report(self.data,self.root/"resume",lambda x:called.append(x),
                               model_id="stub",previous_report_path=prior)
        self.assertEqual(called,[])
        self.assertFalse((self.root/"resume").exists())

    def test_resume_rejected_research_on_fresh_data_succeeds(self):
        from agent_model_research import model_research
        proposal=lambda p:json.dumps([{"family":"trend","lookback":10 if "validation_only_feedback" not in p else 15,
                                        "slow":50,"rationale":"bounded hypothesis"}])
        smaller=self.root/"earlier.csv"
        with self.data.open("r",encoding="utf-8") as reader, smaller.open("w",encoding="utf-8",newline="") as out:
            out.writelines(reader.readlines()[:401])
        initial=model_research(smaller,self.root/"initial",proposal,model_id="mocked")
        prior=json.loads(Path(initial["report_path"]).read_text(encoding="utf-8"))
        self.assertIsNone(prior["selected"])
        resumed=resume_from_report(self.data,self.root/"resumed",proposal,model_id="mocked",
                                   previous_report_path=initial["report_path"])
        newer=json.loads(Path(resumed["report_path"]).read_text(encoding="utf-8"))
        self.assertTrue(newer["model_feedback_used"])
        self.assertIsNotNone(newer["parent_report_sha256"])
        self.assertFalse(resumed["live_trading_authorized"])

    def test_resume_rejects_tampered_report(self):
        bad=self.root/"modified.json"
        bad.write_text('{"selected":"fake"}',encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"content-addressed"):
            resume_from_report(self.data,self.root/"unused",lambda _:"[]",
                               model_id="stub",previous_report_path=bad)

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

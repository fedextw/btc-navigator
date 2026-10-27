import json
import csv
import io
import tempfile
from pathlib import Path
from datetime import datetime,timedelta,timezone
from contextlib import redirect_stdout
import unittest
import urllib.error
from unittest.mock import patch
from agent_llm_adapter import openai_compatible_model, main

class FakeResponse:
    def __init__(self,data):
        self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.data[:n]

class AdapterTests(unittest.TestCase):
    def test_safe_chat_request_and_plain_text_response(self):
        response=json.dumps({"choices":[{"message":{"content":"[]"}}]}).encode()
        with patch("agent_llm_adapter.urllib.request.urlopen",return_value=FakeResponse(response)) as http:
            out=openai_compatible_model("ideas",model="research-test",api_key="test-only")
        self.assertEqual(out,"[]")
        request=http.call_args.args[0]
        self.assertEqual(request.get_method(),"POST")
        self.assertEqual(http.call_args.kwargs["timeout"],30)
        payload=json.loads(request.data)
        self.assertEqual(payload["model"],"research-test")
        self.assertNotIn("tools",payload)
        self.assertNotIn("test-only",json.dumps(payload))
    def test_reject_missing_credentials_and_plain_http(self):
        with self.assertRaises(ValueError):
            openai_compatible_model("ideas",model="test",api_key="")
        with self.assertRaises(ValueError):
            openai_compatible_model("ideas",model="test",api_key="secret",endpoint="http://example.com")
    def test_provider_error_does_not_expose_key(self):
        with patch("agent_llm_adapter.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("credential=secret-internal")):
            with self.assertRaises(RuntimeError) as raised:
                openai_compatible_model("ideas",model="test",api_key="secret-internal")
        self.assertNotIn("secret-internal",str(raised.exception))

    def test_malformed_response_rejected(self):
        with patch("agent_llm_adapter.urllib.request.urlopen",
                   return_value=FakeResponse(b'{"choices":[]}')):
            with self.assertRaisesRegex(ValueError,"Malformed model response"):
                openai_compatible_model("ideas",model="test",api_key="unit-test")

    def test_dry_run_validates_locally_without_model_call(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"candles.csv"
            start=datetime(2026,1,1,tzinfo=timezone.utc)
            with path.open("w",newline="",encoding="utf-8") as file:
                writer=csv.writer(file)
                writer.writerow(("time","open","high","low","close","volume"))
                for i in range(400):
                    p=100+i*0.01
                    writer.writerow(((start+timedelta(hours=i)).isoformat(),p,p+1,p-1,p,100))
            with patch("sys.argv",["adapter",str(path),"--out",d,"--model","test","--dry-run"]):
                with patch("agent_llm_adapter.openai_compatible_model") as model:
                    with redirect_stdout(io.StringIO()) as output:
                        main()
                    model.assert_not_called()
            result=json.loads(output.getvalue())
            self.assertEqual(result["candles"],400)
            self.assertFalse(result["model_called"])
            self.assertFalse(result["live_trading_authorized"])

    def test_dry_run_rejects_overlapping_prior_without_model_call(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"candles.csv"
            start=datetime(2026,1,1,tzinfo=timezone.utc)
            with path.open("w",newline="",encoding="utf-8") as file:
                writer=csv.writer(file)
                writer.writerow(("time","open","high","low","close","volume"))
                for i in range(400):
                    p=100+i*.01
                    writer.writerow(((start+timedelta(hours=i)).isoformat(),p,p+1,p-1,p,100))
            prior={"schema":"agent-orchestrator-v1","paper_only":True,
                   "live_trading_authorized":False,"candidate_count":0,
                   "candidates":[],"cost_fraction":.0014,
                   "dataset_sha256":"a"*64,
                   "dataset_latest_utc":"2026-02-01T00:00:00+00:00"}
            prior_path=Path(d)/"prior.json"
            prior_path.write_text(json.dumps(prior),encoding="utf-8")
            with patch("sys.argv",["adapter",str(path),"--out",d,"--model","test",
                                   "--dry-run","--prior",str(prior_path)]):
                with patch("agent_llm_adapter.openai_compatible_model") as model:
                    with self.assertRaisesRegex(ValueError,"overlaps"):
                        main()
                    model.assert_not_called()

    def test_response_limit(self):
        with patch("agent_llm_adapter.urllib.request.urlopen",return_value=FakeResponse(b"x"*32769)):
            with self.assertRaises(ValueError):
                openai_compatible_model("ideas",model="test",api_key="test")
if __name__=="__main__":
    unittest.main()

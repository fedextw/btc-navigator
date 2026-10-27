import json
import unittest
import urllib.error
from unittest.mock import patch
from agent_llm_adapter import openai_compatible_model

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

    def test_response_limit(self):
        with patch("agent_llm_adapter.urllib.request.urlopen",return_value=FakeResponse(b"x"*32769)):
            with self.assertRaises(ValueError):
                openai_compatible_model("ideas",model="test",api_key="test")
if __name__=="__main__":
    unittest.main()

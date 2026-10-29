import json
import os
import unittest
from unittest.mock import patch
from agent_model_connection import verify_model_connection

class ModelConnectionTests(unittest.TestCase):
    def test_dry_run_never_calls_model(self):
        with patch.dict(os.environ,{"OPENAI_API_KEY":""}):
            result=verify_model_connection(dry_run=True)
        self.assertFalse(result["model_called"])
        self.assertFalse(result["live_trading_authorized"])
    def test_real_call_requires_local_key(self):
        with patch.dict(os.environ,{"OPENAI_API_KEY":""}):
            with self.assertRaisesRegex(ValueError,"OPENAI_API_KEY"):
                verify_model_connection()
    def test_stub_provider_validates_bounded_strategy(self):
        proposal=[{"family":"trend","lookback":10,"slow":50,"rationale":"offline connectivity"}]
        result=verify_model_connection(provider=lambda _:json.dumps(proposal))
        self.assertTrue(result["bounded_strategy_valid"])
        self.assertFalse(result["live_trading_authorized"])
    def test_invalid_model_proposal_rejected(self):
        with self.assertRaises(ValueError):
            verify_model_connection(provider=lambda _:'[]')
if __name__=="__main__":
    unittest.main()

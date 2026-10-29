import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
import agent_stage_four_candle_preflight as m

class PublicOnlyDiagnosticTests(unittest.TestCase):
    def test_4usdt_insufficient_data_returns_no_paid_calls(self):
        with patch("sys.argv",["preflight","--symbol","4USDT"]),\
             patch.object(m,"enough_closed_history",return_value=False) as check:
            output=io.StringIO()
            with redirect_stdout(output):
                code=m.main()
            result=json.loads(output.getvalue())
            self.assertEqual(code,1)
            self.assertEqual(result["status"],"insufficient_history")
            self.assertEqual(result["openai_calls"],0)
            check.assert_called_once_with("4USDT",interval="1h",count=1600,verify_full_window=True)

if __name__=="__main__":unittest.main()

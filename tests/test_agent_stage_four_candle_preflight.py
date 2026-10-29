import json
import unittest
from agent_stage_four_candle_preflight import enough_closed_history

class CandlePreflightTests(unittest.TestCase):
    def test_insufficient_contract_history_is_excluded_before_model_call(self):
        now=2000000000000
        hour=3600000
        latest_start=(now//hour-1)*hour
        def mock(earliest):
            class Resp:
                def __enter__(self):return self
                def __exit__(self,*args):return False
                def read(self,*args):return json.dumps([[earliest, "1", "1", "1", "1", "1", earliest+hour-1]]).encode()
            return lambda *args,**kwargs:Resp()
        self.assertFalse(enough_closed_history("4USDT",now_ms=now,
            count=1600,fetch=mock(latest_start-100*hour)))
        self.assertTrue(enough_closed_history("BTCUSDT",now_ms=now,
            count=1600,fetch=mock(latest_start-2000*hour)))
    def test_public_history_errors_fail_closed(self):
        class Resp:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,*args):return b'{"code":-1121,"msg":"invalid symbol"}'
        with self.assertRaises(ValueError):
            enough_closed_history("4USDT",fetch=lambda *args,**kw:Resp())
if __name__=="__main__":unittest.main()

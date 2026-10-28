import json
import tempfile
import unittest
from pathlib import Path
from agent_stage_four_rotation import run_rotation

class Response:
    def __init__(self,objects):
        self.data=json.dumps({"symbols":[{"symbol":s,"quoteAsset":"USDT",
                      "marginAsset":"USDT","contractType":"PERPETUAL",
                      "status":"TRADING"} for s in objects]}).encode()
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def read(self,n):return self.data[:n]

class RotationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def test_rotation_advances_on_success_only(self):
        symbols=[f"ASSET{i:02d}USDT" for i in range(12)]
        calls=[]
        def fetch(*args,**kwargs):return Response(symbols)
        def runner(state,prior,**kw):
            calls.append(kw["symbol"])
            return {"status":"completed"}
        a=run_rotation(self.root,slot="hour1",fetch=fetch,runner=runner)
        b=run_rotation(self.root,slot="hour1",fetch=fetch,runner=runner)
        c=run_rotation(self.root,slot="hour2",fetch=fetch,runner=runner)
        self.assertEqual(a["next_offset"],10)
        self.assertEqual(b["status"],"already_processed")
        self.assertEqual(c["next_offset"],0)
        self.assertEqual(len(calls),12)
        self.assertFalse(c["live_trading_authorized"])
    def test_failure_halts_cursor_and_next_slot(self):
        def fail(*a,**kw):return {"status":"requires_manual_review"}
        one=run_rotation(self.root,slot="hour1",
            fetch=lambda *a,**kw:Response(["BTCUSDT"]),runner=fail)
        self.assertEqual(one["status"],"requires_manual_review")
        two=run_rotation(self.root,slot="hour2",
            fetch=lambda *a,**kw:Response(["BTCUSDT"]),runner=fail)
        self.assertEqual(two["status"],"requires_manual_review")
        cursor=json.loads((self.root/"stage4-universe-cursor.json").read_text())
        self.assertEqual(cursor["status"],"reserved")
if __name__=="__main__":
    unittest.main()

import json
import unittest
from agent_stage_four_universe import discover,URL

class FakeResponse:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,limit):return self.data[:limit]

class StageFourUniverseTests(unittest.TestCase):
    def test_only_active_usdt_margined_perpetual_contracts(self):
        def contract(symbol,quote="USDT",margin="USDT",kind="PERPETUAL",status="TRADING"):
            return {"symbol":symbol,"quoteAsset":quote,"marginAsset":margin,
                    "contractType":kind,"status":status}
        data={"symbols":[contract("BTCUSDT"),contract("ETHUSDT"),
                         contract("SOLUSDT"),contract("BTCUSDT"),
                         contract("BNBUSDT",kind="CURRENT_QUARTER"),
                         contract("XRPUSDT",status="BREAK"),
                         contract("FOOUSDT",margin="USDC"),
                         contract("BARUSDC",quote="USDC",margin="USDC")]}
        calls=[]
        def fetch(url,timeout):
            calls.append((url,timeout))
            return FakeResponse(json.dumps(data).encode())
        result=discover(fetch=fetch,limit=2,offset=1)
        self.assertEqual(result["eligible_total"],3)
        self.assertEqual(result["symbols"],["ETHUSDT","SOLUSDT"])
        self.assertTrue(result["has_more"] is False)
        self.assertEqual(calls,[(URL,20)])
        self.assertFalse(result["live_trading_authorized"])
    def test_rejects_out_of_bounds_before_network(self):
        called=[]
        with self.assertRaises(ValueError):
            discover(limit=11,fetch=lambda *a,**k:called.append(True))
        self.assertFalse(called)
    def test_reject_oversized_provider_response(self):
        with self.assertRaisesRegex(ValueError,"Oversized"):
            discover(fetch=lambda *a,**k:FakeResponse(b"x"*2000001))
if __name__=="__main__":
    unittest.main()

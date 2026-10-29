import json
import unittest
from agent_stage_four_universe import discover

class StageFourNewMarketFilteringTests(unittest.TestCase):
    def test_freshly_listed_symbol_excluded_before_paid_research(self):
        fixed=2000000000000
        contracts=[
          {"symbol":"4USDT","quoteAsset":"USDT","marginAsset":"USDT","status":"TRADING",
           "contractType":"PERPETUAL","onboardDate":fixed-2*3600000},
          {"symbol":"BTCUSDT","quoteAsset":"USDT","marginAsset":"USDT","status":"TRADING",
           "contractType":"PERPETUAL","onboardDate":fixed-365*86400000}]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,*args):return json.dumps({"symbols":contracts}).encode()
        result=discover(fetch=lambda *a,**kw:Response(),now_ms=fixed,
                        minimum_history_ms=1600*3600000)
        self.assertEqual(result["symbols"],["BTCUSDT"])
        self.assertEqual(result["eligible_total"],1)
    def test_missing_listing_date_does_not_invent_one(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,*args):
                return json.dumps({"symbols":[{"symbol":"BTCUSDT",
                    "quoteAsset":"USDT","marginAsset":"USDT",
                    "status":"TRADING","contractType":"PERPETUAL"}]}).encode()
        self.assertEqual(discover(fetch=lambda *a,**kw:Response(),
                     minimum_history_ms=1600*3600000)["symbols"],["BTCUSDT"])

if __name__=="__main__":unittest.main()

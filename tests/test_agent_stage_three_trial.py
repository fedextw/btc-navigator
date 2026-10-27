import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from agent_stage_three_trial import run_stage_three_trial
from agent_binance_public_candles import download_public_candles

class FakeResponse:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,_):return self.data

class PublicResearchTrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        # All candles are safely historical, hourly spaced and deterministic.
        start=datetime(2025,1,1,tzinfo=timezone.utc)
        self.rows=[]
        for i in range(1600):
            millis=int((start+timedelta(hours=i)).timestamp()*1000)
            price=100+i*.025
            self.rows.append([millis,str(price),str(price+1),str(price-1),
                              str(price), "100",millis+3599999])
    def fetch(self,url,timeout):
        from urllib.parse import urlsplit,parse_qs
        query=parse_qs(urlsplit(url).query)
        max_time=int(query["endTime"][0])
        count=int(query["limit"][0])
        rows=[r for r in self.rows if r[0]<=max_time]
        return FakeResponse(json.dumps(rows[-count:]).encode())
    def test_one_command_trial_uses_public_data_and_stops_without_promotion(self):
        calls=[]
        def model(prompt):
            calls.append(prompt)
            return json.dumps([{"family":"trend","lookback":10+len(calls),"slow":50,
                                "rationale":"offline bounded hypothesis"}])
        report=run_stage_three_trial(self.root/"trial",count=1600,fetch=self.fetch,propose=model)
        self.assertEqual(report["market"]["candles"],1600)
        self.assertEqual(report["research"]["completed_generations"],2)
        self.assertEqual(len(calls),2)
        self.assertFalse(report["acceptance"]["accepted"])
        self.assertFalse(report["live_trading_authorized"])
        self.assertTrue((self.root/"trial"/"trial_summary.json").exists())
    def test_rejects_reusing_existing_trial_location(self):
        (self.root/"existing").mkdir()
        (self.root/"existing"/"prior.txt").write_text("evidence")
        with self.assertRaises(FileExistsError):
            run_stage_three_trial(self.root/"existing",fetch=self.fetch,
                                  propose=lambda _: "[]")
    def test_public_download_rejects_invalid_symbol_without_request(self):
        with self.assertRaises(ValueError):
            download_public_candles(self.root/"bad.csv",symbol="BTCUSDT/evil",fetch=self.fetch)
if __name__=="__main__":
    unittest.main()

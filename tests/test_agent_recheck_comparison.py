import unittest
import json
import hashlib
import tempfile
from pathlib import Path
from agent_recheck_comparison import compare_research_recheck

class RecheckComparisonTests(unittest.TestCase):
    def test_no_proven_improvement_with_researched_replacement(self):
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td)/"agent-frozen-paper-candidates"
            directory.mkdir()
            raw=json.dumps({"paper_only":True,"symbol":"BTCUSDT",
                            "strategy":"trend_8_30"}).encode()
            digest=hashlib.sha256(raw).hexdigest()
            (directory/(digest+".json")).write_bytes(raw)
            research={"live_trading_authorized":False,"items":[
                {"symbol":"BTCUSDT","status":"completed",
                 "result":{"selected":"breakout_20","bars":3000}}]}
            outcome=compare_research_recheck(td,digest,research)
            self.assertEqual(outcome["new_candidate"],"breakout_20")
            self.assertFalse(outcome["independent_improvement_proven"])
            self.assertFalse(outcome["live_trading_authorized"])

    def test_verified_new_cutoff_is_recorded_without_claiming_improvement(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            folder=root/"agent-frozen-paper-candidates"
            folder.mkdir()
            old={"paper_only":True,"symbol":"BTCUSDT",
                 "strategy":"trend_8_30",
                 "historical_cutoff_utc":"2026-01-01T00:00:00+00:00"}
            raw=json.dumps(old).encode()
            digest=hashlib.sha256(raw).hexdigest()
            (folder/(digest+".json")).write_bytes(raw)
            report=root/"new-report.json"
            report.write_text(json.dumps({
                "selected":"breakout_20",
                "config":{"heldout_end":"2026-02-01T00:00:00+00:00"}}))
            recheck={"live_trading_authorized":False,"items":[{
                "symbol":"BTCUSDT","status":"completed",
                "result":{"selected":"breakout_20","bars":1000,
                          "report_path":str(report)}}]}
            result=compare_research_recheck(td,digest,recheck)
            self.assertEqual(result["new_research_cutoff_utc"],
                             "2026-02-01T00:00:00+00:00")
            self.assertEqual(result["status"],
                             "awaiting_fresh_independent_comparison")
            self.assertFalse(result["independent_improvement_proven"])
            report.write_text(json.dumps({
                "selected":"breakout_20",
                "config":{"heldout_end":"2025-12-31T00:00:00+00:00"}}))
            with self.assertRaises(ValueError):
                compare_research_recheck(td,digest,recheck)

    def test_bad_fingerprint_rejected(self):
        with self.assertRaises(ValueError):
            compare_research_recheck('.', 'invalid', {'live_trading_authorized':False})

if __name__ == '__main__':
    unittest.main()

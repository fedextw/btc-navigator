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

    def test_bad_fingerprint_rejected(self):
        with self.assertRaises(ValueError):
            compare_research_recheck('.', 'invalid', {'live_trading_authorized':False})

if __name__ == '__main__':
    unittest.main()

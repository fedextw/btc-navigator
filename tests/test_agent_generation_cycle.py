import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agent_generation_cycle import run_generations

class GenerationCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.csv=self.root/"market.csv"
        origin=datetime(2026,1,1,tzinfo=timezone.utc)
        with self.csv.open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f)
            w.writerow(("time","open","high","low","close","volume"))
            for i in range(1000):
                p=100+i*.06+(i%7)*.01
                w.writerow(((origin+timedelta(hours=i)).isoformat(),p,p+1,p-1,p+.04,100))

    def test_two_generations_save_lineage_with_no_orders(self):
        answer=run_generations(self.csv,self.root/"records",[400,1000])
        self.assertEqual(answer["generations"],2)
        self.assertFalse(answer["live_trading_authorized"])
        first,second=[json.loads(Path(p).read_text(encoding="utf-8")) for p in answer["evidence_paths"]]
        self.assertEqual(first["source"],"pre_registered_parameter_grammar")
        self.assertEqual(second["source"],"validation_guided_evolution")
        self.assertIsNotNone(second["parent_report_sha256"])
        self.assertGreater(second["validation_start_utc"], first["dataset_latest_utc"])

    def test_reject_overlapping_validation_and_no_partial_output(self):
        output=self.root/"overlap"
        with self.assertRaises(ValueError):
            run_generations(self.csv,output,[400,600])
        self.assertFalse(output.exists())

    def test_reject_overwrite(self):
        output=self.root/"immutable"
        run_generations(self.csv,output,[400])
        with self.assertRaises(FileExistsError):
            run_generations(self.csv,output,[400])

    def test_no_qualified_parent_stops_before_second_generation(self):
        output=self.root/"stopped"
        fake={"schema":"agent-orchestrator-v1","selected":None,
              "source":"pre_registered_parameter_grammar",
              "paper_only":True,"live_trading_authorized":False}
        with patch("agent_generation_cycle.experiment", return_value=fake) as runner:
            result=run_generations(self.csv,output,[400,1000])
        self.assertEqual(runner.call_count,1)
        self.assertEqual(result["generations"],1)
        self.assertEqual(result["requested_generations"],2)
        self.assertEqual(result["stop_reason"],"no_qualified_parent_for_next_generation")
        self.assertFalse(result["live_trading_authorized"])

    def test_bounded_generations(self):
        with self.assertRaises(ValueError):
            run_generations(self.csv,self.root/"bad",[300,400,600,1000])

if __name__=="__main__":
    unittest.main()

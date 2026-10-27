"""Two-generation offline model-feedback experiment.

This is an explicit single-process research operation, NOT a background agent.
No trading, no automatic promotion. Each generation uses an immutable CSV
prefix; the second needs genuinely new validation candles.
"""
import csv
import json
import tempfile
from pathlib import Path

from agent_csv_research import read_candles
from agent_model_research import model_research
from agent_model_feedback import research_with_feedback

def run_model_feedback_cycle(csv_path, output_dir, model_fn, *, model_id,
                             first_cutoff, second_cutoff, cost=0.0014):
    if type(first_cutoff) is not int or type(second_cutoff) is not int:
        raise ValueError("Generation cutoffs must be integers")
    candles,_=read_candles(csv_path)
    if first_cutoff < 300 or second_cutoff <= first_cutoff or second_cutoff > len(candles):
        raise ValueError("Invalid generation boundaries")
    target=Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError("Cannot overwrite previous model research")
    with tempfile.TemporaryDirectory() as tmp:
        snapshots=[]
        for index, cutoff in enumerate((first_cutoff,second_cutoff)):
            path=Path(tmp)/("generation_%d.csv"%index)
            with path.open("w",newline="",encoding="utf-8") as handle:
                writer=csv.writer(handle)
                writer.writerow(("time","open","high","low","close","volume"))
                for bar in candles[:cutoff]:
                    writer.writerow((bar[0].isoformat(),*bar[1:]))
            snapshots.append(path)
        # Require chronological independence before either model invocation.
        if candles[int(second_cutoff*.6)][0] <= candles[first_cutoff-1][0]:
            raise ValueError("Second generation overlaps earlier research")
        first=model_research(snapshots[0],target,model_fn,model_id=model_id,cost=cost)
        prior=json.loads(Path(first["report_path"]).read_text(encoding="utf-8"))
        if prior.get("paper_only") is not True or prior.get("live_trading_authorized") is not False:
            raise ValueError("Unsafe first-generation report")
        if prior["selected"] is None:
            return {"schema":"agent-model-cycle-v1","completed_generations":1,
                    "stop_reason":"no_qualified_parent",
                    "reports":[first["report_path"]],"paper_only":True,
                    "live_trading_authorized":False}
        second=research_with_feedback(snapshots[1],target,model_fn,model_id=model_id,
                                      prior=prior,cost=cost)
        latest=json.loads(Path(second["report_path"]).read_text(encoding="utf-8"))
        if latest.get("parent_report_sha256") is None or latest.get("model_feedback_used") is not True:
            raise ValueError("Second-generation lineage evidence missing")
        return {"schema":"agent-model-cycle-v1","completed_generations":2,
                "stop_reason":None,
                "reports":[first["report_path"],second["report_path"]],
                "paper_only":True,"live_trading_authorized":False}

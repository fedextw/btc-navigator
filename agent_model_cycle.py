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

def resume_from_report(new_csv_path, output_dir, model_fn, *, model_id,
                       previous_report_path, cost=0.0014):
    """Explicit restart from an existing immutable first-generation report.

    Requires a new non-overlapping dataset; never repeats or overwrites prior
    research. This is manual resumption, not unattended scheduling.
    """
    import hashlib
    source=Path(previous_report_path)
    data=source.read_bytes()
    # Content-addressed reports written by save_report are immutable evidence.
    if source.suffix != ".json" or source.stem != hashlib.sha256(data).hexdigest():
        raise ValueError("Previous report is not content-addressed evidence")
    prior=json.loads(data)
    if prior.get("schema") != "agent-orchestrator-v1":
        raise ValueError("Invalid previous generation")
    if prior.get("selected") is None:
        raise ValueError("Cannot resume without a qualified parent")
    if prior.get("paper_only") is not True or prior.get("live_trading_authorized") is not False:
        raise ValueError("Unsafe previous research")
    target=Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError("Cannot overwrite existing research")
    # New temporal evidence is required before the model is called.
    from agent_model_feedback import check_feedback_readiness
    check_feedback_readiness(new_csv_path,prior,cost)
    result=research_with_feedback(new_csv_path,target,model_fn,
                                  model_id=model_id,prior=prior,cost=cost)
    latest=json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    expected=hashlib.sha256(json.dumps(prior,sort_keys=True,ensure_ascii=False,
                                       allow_nan=False).encode("utf-8")).hexdigest()
    if latest.get("parent_report_sha256") != expected or latest.get("model_feedback_used") is not True:
        raise ValueError("Resumed research lineage mismatch")
    return {"schema":"agent-model-resume-v1","report_path":result["report_path"],
            "parent_report_sha256":expected,"paper_only":True,
            "live_trading_authorized":False}

def main():
    """Explicit CLI for offline first/second generation and later resume."""
    import argparse
    from agent_llm_adapter import openai_compatible_model
    parser=argparse.ArgumentParser(description="受控 AI 跨代研究及恢復（僅紙上研究）")
    parser.add_argument("csv")
    parser.add_argument("--out",required=True)
    parser.add_argument("--model",required=True)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--resume",help="Immutable prior report JSON path")
    modes.add_argument("--first-cutoff",type=int)
    parser.add_argument("--second-cutoff",type=int)
    args=parser.parse_args()
    provider=lambda prompt:openai_compatible_model(prompt,model=args.model)
    if args.resume:
        if args.second_cutoff is not None:
            parser.error("--second-cutoff is only valid with --first-cutoff")
        result=resume_from_report(args.csv,args.out,provider,model_id=args.model,
                                  previous_report_path=args.resume)
    else:
        if args.second_cutoff is None:
            parser.error("--second-cutoff is required with --first-cutoff")
        result=run_model_feedback_cycle(args.csv,args.out,provider,model_id=args.model,
                                        first_cutoff=args.first_cutoff,
                                        second_cutoff=args.second_cutoff)
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    main()

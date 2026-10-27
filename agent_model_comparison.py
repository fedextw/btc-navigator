"""Fair, bounded, paper-only A/B comparison of model hypothesis proposals.

All models see the same frozen CSV; identical validation and fee rules apply.
This research ranking is NOT out-of-sample proof or authorization to trade.
"""
import argparse
import json
from pathlib import Path
from agent_csv_research import read_candles, COST
from agent_llm_adapter import openai_compatible_model
from agent_model_research import model_research

def compare_models(csv_path, out_dir, *, models=("gpt-4.1-mini","gpt-5.4-mini"),
                   cost=COST, provider=None):
    if not isinstance(models,(list,tuple)) or not 2<=len(models)<=3:
        raise ValueError("Choose 2-3 models")
    if len(set(models))!=len(models) or any(
            not isinstance(m,str) or not m or len(m)>100 or "/" in m or "\\" in m
            for m in models):
        raise ValueError("Invalid or duplicate model names")
    if not 0<=cost<=.1:
        raise ValueError("Invalid cost assumption")
    _,fingerprint=read_candles(csv_path)
    root=Path(out_dir)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("Comparison directory must be empty")
    root.mkdir(parents=True,exist_ok=True)
    entries=[]
    for index,model in enumerate(models):
        # Never share model feedback during comparisons: independent candidate generation.
        propose=(lambda prompt,m=model:provider(m,prompt)) if provider is not None else (
            lambda prompt,m=model:openai_compatible_model(prompt,model=m))
        run=model_research(csv_path,root/("model_%d"%index),propose,model_id=model,
                           cost=cost,expected_dataset_sha256=fingerprint)
        report=json.loads(Path(run["report_path"]).read_text(encoding="utf-8"))
        if report["dataset_sha256"]!=fingerprint:
            raise ValueError("Research datasets differ")
        eligible=[c for c in report["candidates"] if c["status"]=="validation_pass"]
        best=max((c["validation"]["net_expectancy_r"] for c in report["candidates"]),default=None)
        entries.append({"model":model,"report_path":run["report_path"],
                        "candidate_count":report["candidate_count"],
                        "qualified_count":len(eligible),
                        "best_validation_net_expectancy_r":best,
                        "paper_only":True})
    result={"schema":"agent-model-comparison-v1","dataset_sha256":fingerprint,
            "cost_fraction":cost,"models":entries,
            "comparison_scope":"same_dataset_validation_only",
            "heldout_untouched":True,"paper_only":True,
            "live_trading_authorized":False,
            "note":"Model candidate quality comparison, not a forecast or live promotion."}
    (root/"comparison_summary.json").write_text(json.dumps(result,ensure_ascii=False,
        sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return result

def main():
    p=argparse.ArgumentParser(description="Compare 2-3 LLMs on one frozen paper research dataset")
    p.add_argument("csv")
    p.add_argument("--out",required=True)
    p.add_argument("--models",nargs="+",default=["gpt-4.1-mini","gpt-5.4-mini"])
    p.add_argument("--cost",type=float,default=COST)
    args=p.parse_args()
    result=compare_models(args.csv,args.out,models=args.models,cost=args.cost)
    print(json.dumps({"summary":str(Path(args.out)/"comparison_summary.json"),
       "dataset_sha256":result["dataset_sha256"],"models":result["models"],
       "paper_only":True},ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()

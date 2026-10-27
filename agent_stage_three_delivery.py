"""Single-command stage-three delivery audit: live two-generation trial and frozen-data A/B.

Explicit user invocation only, paper-only. Existing artifacts are immutable.
The final acceptance is engineering evidence, NOT profitable strategy approval.
"""
import argparse
import json
from pathlib import Path
from agent_stage_three_trial import run_stage_three_trial
from agent_model_comparison import compare_models

def run_delivery(out, *, symbol="BTCUSDT", interval="1h", count=1600,
                 model="gpt-4.1-mini", comparison_models=None,
                 fetch=None, propose=None, comparison_provider=None):
    models=tuple(comparison_models or ("gpt-4.1-mini","gpt-5.4-mini"))
    root=Path(out)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("Choose a new empty stage-three delivery directory")
    root.mkdir(parents=True,exist_ok=True)
    trial=run_stage_three_trial(root/"trial",symbol=symbol,interval=interval,
                                count=count,model=model,fetch=fetch,propose=propose)
    comparison=compare_models(trial["market"]["csv"],root/"comparison",
                               models=models,provider=comparison_provider)
    if trial["market"]["dataset_sha256"]!=comparison["dataset_sha256"]:
        raise ValueError("Comparison dataset differs from research trial")
    accepted=trial["acceptance"]["accepted"]
    result={"schema":"agent-stage-three-delivery-v1",
            "dataset_sha256":trial["market"]["dataset_sha256"],
            "trial_summary":str(root/"trial"/"trial_summary.json"),
            "comparison_summary":str(root/"comparison"/"comparison_summary.json"),
            "trial_completed_generations":trial["research"]["completed_generations"],
            "trial_provider_verified":trial["provider_verified_by_live_calls"],
            "trial_engineering_accepted":accepted,
            "comparison_models":[m["model"] for m in comparison["models"]],
            "engineering_accepted":accepted,
            "model_comparison_scope":"same_dataset_validation_only",
            "profitability_proven":False,"paper_only":True,
            "live_trading_authorized":False}
    (root/"delivery_summary.json").write_text(
        json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",
        encoding="utf-8")
    return result

def main():
    p=argparse.ArgumentParser(description="Complete stage-three engineering and model A/B research delivery")
    p.add_argument("--out",required=True)
    p.add_argument("--symbol",default="BTCUSDT")
    p.add_argument("--interval",default="1h")
    p.add_argument("--count",type=int,default=1600)
    p.add_argument("--model",default="gpt-4.1-mini")
    p.add_argument("--comparison-models",nargs="+",default=["gpt-4.1-mini","gpt-5.4-mini"])
    a=p.parse_args()
    result=run_delivery(a.out,symbol=a.symbol,interval=a.interval,count=a.count,
                        model=a.model,comparison_models=a.comparison_models)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result["engineering_accepted"]:
        raise SystemExit(2)
if __name__=="__main__":
    main()

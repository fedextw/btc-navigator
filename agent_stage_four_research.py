"""Stage-four bounded autonomous research step.

One explicit invocation: download fresh closed public candles, consume an
immutable prior report, ask one bounded model question, and save evidence.
No background loop, no brokerage keys, no execution or strategy promotion.
"""
import argparse
import hashlib
import json
from pathlib import Path
from agent_binance_public_candles import download_public_candles
from agent_model_cycle import resume_from_report
from agent_llm_adapter import openai_compatible_model

def run_step(workspace, prior_report, *, symbol="BTCUSDT", interval="1h",
             count=1600, model="gpt-4.1-mini", fetch=None, propose=None):
    root=Path(workspace)
    parent=Path(prior_report)
    if not parent.is_file():
        raise FileNotFoundError("Prior immutable research report required")
    raw=parent.read_bytes()
    if parent.stem!=hashlib.sha256(raw).hexdigest() or parent.suffix!=".json":
        raise ValueError("Prior report lacks content-address verification")
    previous=json.loads(raw)
    if (previous.get("paper_only") is not True or
            previous.get("live_trading_authorized") is not False or
            previous.get("schema")!="agent-orchestrator-v1"):
        raise ValueError("Unsafe prior research provenance")
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("Stage-four workspace must be empty: never overwrite evidence")
    root.mkdir(parents=True,exist_ok=True)
    snapshot=download_public_candles(root/"market.csv",symbol=symbol,
                                    interval=interval,count=count,fetch=fetch)
    provider=propose if propose is not None else (
        lambda prompt:openai_compatible_model(prompt,model=model))
    # resume_from_report checks chronological independence before invoking LLM.
    result=resume_from_report(snapshot["csv"],root/"reports",provider,
                              model_id=model,previous_report_path=parent)
    report=json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    summary={"schema":"agent-stage4-research-step-v1",
             "market":snapshot,"model":model,"report_path":result["report_path"],
             "parent_report_sha256":result["parent_report_sha256"],
             "model_provider_path":"live" if propose is None else "injected_test",
             "candidate_count":report["candidate_count"],
             "qualified_count":sum(c.get("status")=="validation_pass" for c in report["candidates"]),
             "selected":report.get("selected"),
             "step_status":"completed_research" if report.get("selected") else "no_qualified_candidate",
             "paper_only":True,"live_trading_authorized":False,
             "automatic_promotion":False}
    (root/"step_summary.json").write_text(json.dumps(summary,ensure_ascii=False,
              sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return summary

def main():
    p=argparse.ArgumentParser(description="Bounded stage-four one-generation research update; no trading")
    p.add_argument("--out",required=True)
    p.add_argument("--prior-report",required=True)
    p.add_argument("--symbol",default="BTCUSDT")
    p.add_argument("--interval",default="1h")
    p.add_argument("--count",type=int,default=1600)
    p.add_argument("--model",default="gpt-4.1-mini")
    args=p.parse_args()
    print(json.dumps(run_step(args.out,args.prior_report,symbol=args.symbol,
         interval=args.interval,count=args.count,model=args.model),ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()

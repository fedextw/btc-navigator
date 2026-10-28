"""Opt-in stage-four checkpointed research worker: at most one model call per slot.

Fail closed on interrupted slots: never retry potentially charged model work
automatically. A human may inspect immutable reports before resetting state.
"""
import argparse
import json
import os
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from agent_single_instance import research_lock
from agent_stage_four_research import run_step

def _atomic(path, payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,
                                     delete=False,suffix=".tmp") as stream:
        json.dump(payload,stream,sort_keys=True,ensure_ascii=False,allow_nan=False)
        temp=stream.name
    os.replace(temp,path)

def run_checkpointed(state_dir, prior_report, *, slot, runner=run_step,
                     symbol="BTCUSDT",interval="1h",count=1600,model="gpt-4.1-mini"):
    if not isinstance(slot,str) or not 1<=len(slot)<=48 or not all(c.isalnum() or c in "-_" for c in slot):
        raise ValueError("Invalid schedule slot")
    root=Path(state_dir)
    with research_lock(root):
        checkpoint=root/"stage4-checkpoint.json"
        previous=None
        if checkpoint.is_file():
            if checkpoint.stat().st_size>8192:
                raise ValueError("Oversized stage-four checkpoint")
            previous=json.loads(checkpoint.read_text(encoding="utf-8"))
            if previous.get("schema")!="agent-stage4-checkpoint-v1" or previous.get("live_trading_authorized") is not False:
                raise ValueError("Unsafe or invalid stage-four checkpoint")
            if previous.get("slot")==slot:
                return {"status":"already_completed" if previous.get("status")=="completed" else "requires_manual_review",
                        "slot":slot,"paper_only":True,"live_trading_authorized":False}
            if previous.get("status")!="completed":
                return {"status":"requires_manual_review","slot":slot,"paper_only":True,
                        "live_trading_authorized":False}
        # Advance only from last successfully saved report.
        selected_parent=prior_report
        if previous is not None:
            if (previous.get("symbol")!=symbol or previous.get("interval")!=interval
                    or previous.get("model")!=model):
                raise ValueError("Research lineage settings changed")
            selected_parent=previous.get("report_path")
            if not isinstance(selected_parent,str) or not Path(selected_parent).is_file():
                raise ValueError("Previous completed report missing")
        elif prior_report is not None and not isinstance(prior_report,(str,Path)):
            raise ValueError("Invalid initial report")
        # Slot reservation happens before external I/O or any billable model call.
        now=datetime.now(timezone.utc).isoformat()
        base={"schema":"agent-stage4-checkpoint-v1","slot":slot,"status":"reserved",
              "started_at_utc":now,"symbol":symbol,"interval":interval,"model":model,
              "paper_only":True,"live_trading_authorized":False}
        _atomic(checkpoint,base)
        out=root/"steps"/slot
        try:
            result=runner(out,selected_parent,symbol=symbol,interval=interval,
                          count=count,model=model)
        except Exception as exc:
            # Keep reserved state. A request might have been billed. Record only
            # safe diagnostic metadata; never persist exception messages because
            # upstream HTTP errors can contain sensitive request parameters.
            # A missing market.csv is a clue, NOT proof no model call occurred.
            _atomic(root/"failure-diagnostic.json", {
                "schema":"agent-stage4-failure-diagnostic-v1",
                "slot":slot,"symbol":symbol,"interval":interval,
                "exception_type":type(exc).__name__,
                "market_csv_saved":(out/"market.csv").is_file(),
                "model_charge_status":"unknown",
                "requires_manual_review":True,
                "paper_only":True,"live_trading_authorized":False,
                "failed_at_utc":datetime.now(timezone.utc).isoformat()})
            raise
        if result.get("paper_only") is not True or result.get("live_trading_authorized") is not False:
            raise ValueError("Unsafe research output")
        finished=dict(base,status="completed",report_path=result["report_path"],
                      finished_at_utc=datetime.now(timezone.utc).isoformat())
        _atomic(checkpoint,finished)
        return {"status":"completed","slot":slot,"report_path":result["report_path"],
                "paper_only":True,"live_trading_authorized":False}

def main():
    p=argparse.ArgumentParser(description="One stage-four research slot, no auto retry or trading")
    p.add_argument("--state-dir",required=True)
    p.add_argument("--prior-report",required=True)
    p.add_argument("--slot",required=True)
    p.add_argument("--symbol",default="BTCUSDT")
    p.add_argument("--interval",default="1h")
    p.add_argument("--count",type=int,default=1600)
    p.add_argument("--model",default="gpt-4.1-mini")
    a=p.parse_args()
    print(json.dumps(run_checkpointed(a.state_dir,a.prior_report,slot=a.slot,
         symbol=a.symbol,interval=a.interval,count=a.count,model=a.model),
         ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()

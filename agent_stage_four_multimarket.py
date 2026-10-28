"""Isolated rotating USD-M research slots. No trading or live promotion.

Each symbol/interval has its own checkpoint and lineage. The cross-symbol
scheduler uses a strict local batch; no account keys, no order endpoints.
"""
import argparse
import json
from pathlib import Path
from agent_stage_four_checkpoint import run_checkpointed
from agent_symbol_validation import valid_symbol

def run_batch(state_dir, *, symbols, seed_reports, slot, interval="1h",
              model="gpt-4.1-mini", count=1600, runner=run_checkpointed):
    if (not isinstance(symbols,(tuple,list)) or not 1<=len(symbols)<=10
            or len(symbols)!=len(set(symbols))
            or any(not isinstance(s,str) or not valid_symbol(s) for s in symbols)):
        raise ValueError("Provide 1-10 unique valid USDT contracts")
    if not isinstance(seed_reports,dict) or any(
            not isinstance(seed_reports.get(s),str) or not seed_reports[s]
            for s in symbols):
        raise ValueError("Each contract requires its own immutable seed report")
    items=[]
    for symbol in symbols:
        # Symbol and interval cannot affect other checkpoints or output files.
        isolated=Path(state_dir)/"markets"/symbol/interval
        try:
            record=runner(isolated,seed_reports[symbol],slot=slot,symbol=symbol,
                          interval=interval,model=model,count=count)
            items.append({"symbol":symbol,"status":record["status"],
                          "paper_only":True,"live_trading_authorized":False})
        except (OSError,ValueError,RuntimeError) as exc:
            items.append({"symbol":symbol,"status":"requires_manual_review",
                          "error_type":type(exc).__name__,
                          "paper_only":True,"live_trading_authorized":False})
    return {"schema":"agent-stage4-batch-v1","slot":slot,"items":items,
            "paper_only":True,"live_trading_authorized":False}

def main():
    p=argparse.ArgumentParser(description="Bounded per-market paper research batch")
    p.add_argument("--state-dir",required=True)
    p.add_argument("--slot",required=True)
    p.add_argument("--seeds",required=True,help="JSON symbol-to-immutable-report mapping")
    p.add_argument("--symbols",nargs="+",required=True)
    p.add_argument("--interval",default="1h")
    p.add_argument("--model",default="gpt-4.1-mini")
    p.add_argument("--count",type=int,default=1600)
    a=p.parse_args()
    mapping=json.loads(Path(a.seeds).read_text(encoding="utf-8"))
    print(json.dumps(run_batch(a.state_dir,symbols=a.symbols,seed_reports=mapping,
       slot=a.slot,interval=a.interval,model=a.model,count=a.count),
       ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()

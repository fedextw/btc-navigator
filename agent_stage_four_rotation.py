"""Durable bounded round-robin over active public USDT perpetual markets.

Persist the next offset atomically. Do not advance after an incomplete or
manual-review batch, to avoid silently skipping a failed research slot.
"""
import argparse
import json
import os
import tempfile
from pathlib import Path
from agent_single_instance import research_lock
from agent_stage_four_multimarket import run_discovered_batch
from agent_stage_four_universe import discover
from agent_stage_four_readiness import check_batch_readiness
from agent_stage_four_candle_preflight import enough_closed_history

def _save(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,
                                     delete=False,suffix=".tmp") as out:
        json.dump(data,out,sort_keys=True,ensure_ascii=False,allow_nan=False)
        tmp=out.name
    os.replace(tmp,path)

def run_rotation(state_dir, *, slot, seeds=None, fetch=None, runner=None,
                 interval="1h",model="gpt-4.1-mini",count=1600):
    root=Path(state_dir)
    with research_lock(root/"rotation-control"):
        cursor=root/"stage4-universe-cursor.json"
        previous=None
        if cursor.is_file():
            if cursor.stat().st_size>4096:
                raise ValueError("Oversized rotation cursor")
            previous=json.loads(cursor.read_text(encoding="utf-8"))
            if previous.get("schema")!="agent-stage4-universe-cursor-v1" or previous.get("live_trading_authorized") is not False:
                raise ValueError("Invalid rotation cursor")
            if previous["status"]=="reserved":
                return {"status":"requires_manual_review","paper_only":True,"live_trading_authorized":False}
            if previous["slot"]==slot:
                return {"status":"already_processed","paper_only":True,"live_trading_authorized":False}
            if previous["status"]!="completed":
                raise ValueError("Unrecognized rotation cursor status")
        offset=previous["next_offset"] if previous else 0
        # One snapshot for both selection and research (no inconsistent pages).
        # Exclude contracts that demonstrably cannot supply the requested
        # fully closed candle window before reserving any paid research slot.
        interval_ms={"15m":900000,"1h":3600000,"4h":14400000}
        minimum_history_ms=count*interval_ms[interval]
        universe=discover(fetch=fetch,limit=10,offset=offset,
                          minimum_history_ms=minimum_history_ms)
        if not universe["symbols"] and offset>0:
            offset=0
            universe=discover(fetch=fetch,limit=10,offset=0,
                              minimum_history_ms=minimum_history_ms)
        if not universe["symbols"]:
            return {"status":"empty_universe","paper_only":True,"live_trading_authorized":False}
        page_size=len(universe["symbols"])
        # Real runs must verify the oldest available PUBLIC candle; exchange
        # listing dates alone did not exclude 4USDT in the user's second slot.
        # Fail closed on network errors, before making any model calls.
        if fetch is None:
            verified=[s for s in universe["symbols"] if enough_closed_history(
                s,interval=interval,count=count)]
            universe=dict(universe,symbols=verified)
            if not verified:
                return {"status":"waiting_for_fresh_data","slot":slot,
                        "waiting":[{"reason":"no_selected_market_has_sufficient_history"}],
                        "paper_only":True,"live_trading_authorized":False}
        readiness=check_batch_readiness(root,universe["symbols"],interval=interval,count=count)
        if readiness["status"]!="ready":
            return dict(readiness,offset=offset,slot=slot)
        base={"schema":"agent-stage4-universe-cursor-v1","slot":slot,
              "offset":offset,"status":"reserved","symbols":list(universe["symbols"]),
              "paper_only":True,"live_trading_authorized":False}
        _save(cursor,base)
        # Reuse one discovered selection to avoid a second potentially changed page.
        options={"seed_reports":seeds or {},"slot":slot,"offset":offset,
                 "interval":interval,"model":model,"count":count,
                 "universe_snapshot":universe}
        if runner is not None:
            options["runner"]=runner
        result=run_discovered_batch(root,**options)
        statuses=[item["status"] for item in result["items"]]
        permitted={"completed","already_completed"}
        if not statuses or any(s not in permitted for s in statuses):
            return {"status":"requires_manual_review","offset":offset,"items":result["items"],
                    "paper_only":True,"live_trading_authorized":False}
        next_offset=0 if not universe["has_more"] else offset+page_size
        _save(cursor,dict(base,status="completed",next_offset=next_offset))
        return {"status":"completed","offset":offset,"next_offset":next_offset,
                "items":result["items"],"paper_only":True,"live_trading_authorized":False}

def main():
    p=argparse.ArgumentParser(description="Explicit single rotation batch, no trading")
    p.add_argument("--state-dir",required=True)
    p.add_argument("--slot",required=True)
    p.add_argument("--interval",default="1h")
    p.add_argument("--model",default="gpt-4.1-mini")
    p.add_argument("--count",type=int,default=1600)
    args=p.parse_args()
    print(json.dumps(run_rotation(args.state_dir,slot=args.slot,interval=args.interval,
                                  model=args.model,count=args.count),ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()

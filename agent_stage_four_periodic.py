"""Opt-in bounded periodic stage-four research, with durable slot checkpoints.

Explicit CLI process only. No startup service, no shell execution, no trading.
Slots are UTC periods; a failed/reserved period must be manually reviewed.
"""
import argparse
import json
import time
from datetime import datetime,timezone
from agent_stage_four_checkpoint import run_checkpointed

def utc_slot(now, hours):
    if type(hours) is not int or not 1<=hours<=24 or 24%hours:
        raise ValueError("Interval hours must divide one day")
    if not isinstance(now,datetime) or now.tzinfo is None or now.utcoffset().total_seconds()!=0:
        raise ValueError("Expected aware UTC timestamp")
    start=now.replace(hour=(now.hour//hours)*hours,minute=0,second=0,microsecond=0)
    return start.strftime("%Y%m%dT%HZ")

def run_period(state_dir,prior_report,*,now=None,hours=6,runner=run_checkpointed,
               symbol="BTCUSDT",interval="1h",count=1600,model="gpt-4.1-mini"):
    now=now or datetime.now(timezone.utc)
    slot=utc_slot(now,hours)
    outcome=runner(state_dir,prior_report,slot=slot,symbol=symbol,
                   interval=interval,count=count,model=model)
    return {"schema":"agent-stage4-periodic-v1","slot":slot,
            "status":outcome["status"],"research":outcome,
            "paper_only":True,"live_trading_authorized":False}

def main():
    p=argparse.ArgumentParser(description="Explicit periodic paper research (never auto-starts)")
    p.add_argument("--state-dir",required=True)
    p.add_argument("--prior-report",required=True)
    p.add_argument("--hours",type=int,default=6,choices=[1,2,3,4,6,8,12,24])
    p.add_argument("--once",action="store_true",help="Run exactly one scheduled UTC slot")
    p.add_argument("--max-cycles",type=int,default=4,help="Maximum cycles in this explicit process")
    p.add_argument("--symbol",default="BTCUSDT")
    p.add_argument("--interval",default="1h")
    p.add_argument("--count",type=int,default=1600)
    p.add_argument("--model",default="gpt-4.1-mini")
    a=p.parse_args()
    if not 1<=a.max_cycles<=24:
        p.error("max-cycles must be between 1 and 24")
    for index in range(1 if a.once else a.max_cycles):
        result=run_period(a.state_dir,a.prior_report,hours=a.hours,
                          symbol=a.symbol,interval=a.interval,count=a.count,model=a.model)
        print(json.dumps(result,ensure_ascii=False),flush=True)
        if result["status"]=="requires_manual_review":
            raise SystemExit(2)
        if a.once or index==a.max_cycles-1:
            break
        # Sleep until next UTC slot; no repeated calls within current slot.
        now=datetime.now(timezone.utc)
        delay=a.hours*3600-((now.hour%a.hours)*3600+now.minute*60+now.second)
        time.sleep(max(1,delay))
if __name__=="__main__":
    main()

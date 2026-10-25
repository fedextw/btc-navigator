"""Opt-in periodic paper-forward worker; does nothing until invoked explicitly.

Serial guarded cycles, bounded interval, clean stop, and no live trading.
"""
import argparse
import json
import time
from pathlib import Path
from agent_forward_guarded import guarded_run

def run_periodic(state_dir, *, interval_seconds=3600, cycles=1, sleep=time.sleep, runner=guarded_run):
    if type(interval_seconds) is not int or not 300<=interval_seconds<=86400:
        raise ValueError("研究週期需介於5分鐘與24小時")
    if type(cycles) is not int or not 1<=cycles<=24:
        raise ValueError("單次啟動最多24輪")
    if not Path(state_dir).is_dir():
        raise ValueError("研究資料目錄不存在")
    results=[]
    for n in range(cycles):
        result=runner(state_dir)
        status=result.get("status")
        results.append({"cycle":n+1,"status":status,
                        "registered":(result.get("registered") or {}).get("registered",0),
                        "observed":(result.get("observed") or {}).get("observed",0),
                        "live_trading_authorized":False})
        # Never spin on stale lock or a failed stage.
        if status!="completed":
            break
        if n+1<cycles:
            sleep(interval_seconds)
    return {"schema":"agent-forward-periodic-v1","paper_only":True,
            "live_trading_authorized":False,"cycles":results,
            "status":"completed" if results and all(r["status"]=="completed" for r in results) else "stopped"}

def main():
    p=argparse.ArgumentParser(description="受控前向研究週期執行，僅模擬")
    p.add_argument("--state-dir",required=True)
    p.add_argument("--interval-seconds",type=int,default=3600)
    p.add_argument("--cycles",type=int,default=1)
    a=p.parse_args()
    print(json.dumps(run_periodic(a.state_dir,interval_seconds=a.interval_seconds,
                                  cycles=a.cycles),ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

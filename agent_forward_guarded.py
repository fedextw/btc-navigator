"""Opt-in guarded forward pipeline runner. No daemon, brokerage or trading rights.

Atomic exclusive lock prevents overlap; interrupted runs require explicit
operator cleanup rather than unsafe automatic takeover.
"""
import argparse
import json
import os
from pathlib import Path
from agent_forward_pipeline import run_once

def guarded_run(state_dir, *, now=None):
    root=Path(state_dir)
    if not root.is_dir(): raise ValueError("研究目錄不存在")
    lock=root/"agent-forward-pipeline.lock"
    try:
        fd=os.open(str(lock),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:
        return {"status":"already_running_or_stale_lock","paper_only":True,
                "live_trading_authorized":False}
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as handle:
            handle.write(json.dumps({"purpose":"paper_forward_pipeline","pid":os.getpid()}))
        return run_once(root,now=now)
    finally:
        lock.unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser(description="前向研究受控單次執行，防止重疊")
    p.add_argument("--state-dir",required=True)
    args=p.parse_args()
    print(json.dumps(guarded_run(args.state_dir),ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

"""Opt-in one-shot paper research pipeline, no daemon and no order execution.

Stage failures are reported explicitly; missing data never becomes profitability.
"""
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
from agent_forward_register import register_qualified
from agent_forward_observer import observe_once
from agent_forward_dashboard import summarize_forward
from agent_forward_gap_diagnostic import diagnose

def run_once(state_dir, *, now=None):
    root=Path(state_dir)
    if not root.is_dir():
        raise ValueError("研究資料目錄不存在")
    stamp=now or datetime.now(timezone.utc).isoformat()
    result={"schema":"agent-forward-pipeline-v1","paper_only":True,
            "live_trading_authorized":False,"status":"completed",
            "registered":None,"observed":None,"dashboard":None,"data_integrity":None}
    try:
        result["registered"]=register_qualified(root,max_reports=10,enrolled_at=stamp)
        result["observed"]=observe_once(root,max_enrollments=3,max_bars_each=5,now=stamp)
        if result["observed"].get("skipped",0)>0:
            result["status"]="blocked_observer_errors"
            result["note"]="部分前向策略觀測失敗，暫停本輪績效摘要；請檢查觀測紀錄與資料庫"
            return result
        integrity=diagnose(root,max_enrollments=10)
        result["data_integrity"]={"status":integrity["status"],"checked":integrity["checked"],"gaps":integrity["gaps"]}
        if integrity["status"]=="gaps_found":
            result["status"]="blocked_data_gap"
            result["note"]="前向觀測有缺口或資料異常，暫停績效摘要"
            return result
        view=summarize_forward(root,max_enrollments=12)
        result["dashboard"]={"status":view["status"],"checked":view["checked"],
                            "rows":view["rows"]}
    except (OSError,ValueError,TypeError,KeyError,RuntimeError) as exc:
        result["status"]="error"
        result["error_type"]=type(exc).__name__
        result["note"]="本次研究流程未完整執行；不得解讀為已驗證獲利"
    return result

def main():
    p=argparse.ArgumentParser(description="B+C 前向研究受控單次執行（無真實下單）")
    p.add_argument("--state-dir",required=True)
    args=p.parse_args()
    print(json.dumps(run_once(args.state_dir),ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

"""Read-only diagnostics for a separately installed B+C research instance."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sys

def inspect(state_dir, port=8591):
    state=Path(state_dir).resolve()
    info={"schema":"bc-diagnostic-v1","state_directory_exists":state.is_dir(),
          "port":port,"website_port_responds":False,
          "scanner_log_exists":(state/"scanner.log").is_file(),
          "agent_status":"missing","agent_updated_at":None,
          "agent_paper_only":None,"live_trading_authorized":None,
          "recommendation":"請先啟動 B+C 測試系統"}
    with socket.socket() as sock:
        sock.settimeout(1.0)
        info["website_port_responds"]=sock.connect_ex(("127.0.0.1",port))==0
    path=state/"agent-status"/"latest.json"
    if path.is_file():
        try:
            report=json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(report,dict): raise ValueError("Invalid agent status")
            info["agent_status"]=str(report.get("phase","unknown"))[:32]
            info["agent_updated_at"]=report.get("finished_at") or report.get("started_at")
            info["agent_paper_only"]=report.get("paper_only")
            info["live_trading_authorized"]=report.get("live_trading_authorized")
        except (OSError,ValueError,UnicodeError):
            info["agent_status"]="invalid"
    if info["website_port_responds"] and info["scanner_log_exists"] and info["agent_status"] in ("running","completed"):
        info["recommendation"]="基本啟動狀態正常；仍需確認行情更新及研究紀錄"
    elif info["website_port_responds"]:
        info["recommendation"]="網站連接埠有回應，但掃描器或 Agent 狀態不完整，請查看對應日誌"
    return info

def main():
    parser=argparse.ArgumentParser(description="B+C 研究版唯讀健康診斷")
    parser.add_argument("--state-dir",default=str(Path(__file__).resolve().parent/".agent-test-state"))
    parser.add_argument("--port",type=int,default=8591)
    args=parser.parse_args()
    if not 1024<=args.port<=65535: parser.error("連接埠不合法")
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(errors="backslashreplace")
    print(json.dumps(inspect(args.state_dir,args.port),ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

"""Read-only, fail-closed stage-four per-market evidence rollup."""
import argparse
import hashlib
import json
from pathlib import Path
from agent_symbol_validation import valid_symbol

def inspect(state_dir, *, interval="1h", limit=1000):
    if interval not in ("15m","1h","4h") or type(limit) is not int or not 1<=limit<=1000:
        raise ValueError("Invalid audit selection")
    base=Path(state_dir)/"markets"
    found=[]
    if base.is_dir():
        folders=sorted(p for p in base.iterdir() if p.is_dir())
        if len(folders)>limit: raise ValueError("Too many research markets")
        for folder in folders:
            symbol=folder.name
            if not valid_symbol(symbol): raise ValueError("Invalid market folder")
            check=folder/interval/"stage4-checkpoint.json"
            if not check.is_file(): continue
            if check.stat().st_size>8192: raise ValueError("Oversized checkpoint")
            row=json.loads(check.read_text(encoding="utf-8"))
            if (row.get("schema")!="agent-stage4-checkpoint-v1" or
                    row.get("live_trading_authorized") is not False or
                    row.get("paper_only") is not True or
                    row.get("symbol")!=symbol or row.get("interval")!=interval):
                raise ValueError("Unsafe or mismatched market checkpoint")
            entry={"symbol":symbol,"checkpoint_status":row.get("status"),
                   "slot":row.get("slot"),"report_verified":False,
                   "paper_only":True,"live_trading_authorized":False}
            if row.get("status")=="completed":
                path=Path(row.get("report_path",""))
                if not path.is_file(): raise ValueError("Completed report missing")
                data=path.read_bytes()
                if (len(data)>2_000_000 or path.suffix!=".json" or
                        path.stem!=hashlib.sha256(data).hexdigest()):
                    raise ValueError("Report fingerprint invalid")
                report=json.loads(data)
                if (report.get("schema")!="agent-orchestrator-v1" or
                        report.get("paper_only") is not True or
                        report.get("live_trading_authorized") is not False or
                        type(report.get("candidate_count")) is not int or
                        not isinstance(report.get("candidates"),list) or
                        report["candidate_count"]!=len(report["candidates"])):
                    raise ValueError("Unsafe research report")
                entry.update(report_verified=True,
                             candidates=report["candidate_count"],
                             qualified=sum(x.get("status")=="validation_pass"
                                for x in report["candidates"]),
                             selected=report.get("selected"))
            elif row.get("status")!="reserved":
                raise ValueError("Unknown checkpoint status")
            found.append(entry)
    return {"schema":"agent-stage4-evidence-rollup-v1","interval":interval,
            "markets":found,"markets_checked":len(found),
            "verified_reports":sum(x["report_verified"] for x in found),
            "requires_manual_review":sum(x["checkpoint_status"]=="reserved" for x in found),
            "profitability_proven":False,"paper_only":True,
            "live_trading_authorized":False}

def main():
    p=argparse.ArgumentParser(description="Read-only research evidence rollup")
    p.add_argument("--state-dir",required=True)
    p.add_argument("--interval",default="1h")
    a=p.parse_args()
    print(json.dumps(inspect(a.state_dir,interval=a.interval),ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()

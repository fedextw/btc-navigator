"""Explicit, bounded enrollment of qualified research reports for future-only paper study.

Never trades. Scans local immutable research reports; existing enrollments remain
authoritative across repeated invocations.
"""
import argparse
import hashlib
import json
from pathlib import Path
from agent_forward_enrollment import enroll

def register_qualified(state_dir, *, max_reports=10, enrolled_at=None):
    if type(max_reports) is not int or not 1 <= max_reports <= 10:
        raise ValueError("最多處理10份研究報告")
    root=Path(state_dir)
    folder=root/"agent-cycles"
    result={"checked":0,"registered":0,"existing":0,"rejected":0,
            "status":"paper_only","live_trading_authorized":False}
    if not folder.is_dir():
        return result
    existing=set()
    destination=root/"agent-forward"
    if destination.exists():
        paths=list(destination.glob("*.json"))
        if len(paths)>1000: raise ValueError("前向策略登記過多")
        for path in paths:
            if path.stat().st_size>8192: raise ValueError("前向登記內容過大")
            entry=json.loads(path.read_text(encoding="utf-8"))
            if entry.get("schema")!="agent-forward-enrollment-v1" or entry.get("live_trading_authorized") is not False:
                raise ValueError("存在異常登記，停止")
            existing.add((entry.get("research_sha256"),entry.get("symbol")))
    reports=sorted(folder.glob("*.json"))
    if len(reports)>10000: raise ValueError("研究報告過多")
    for path in reports[:max_reports]:
        result["checked"]+=1
        try:
            if path.stat().st_size>256000: raise ValueError("報告過大")
            report=json.loads(path.read_text(encoding="utf-8"))
            source=report.get("source") if isinstance(report,dict) else None
            symbol=source.get("symbol") if isinstance(source,dict) else None
            if (not symbol or report.get("schema")!="agent-cycle-v1" or
                report.get("paper_status")!="research_candidate" or
                report.get("profitability_evidence",{}).get("eligible") is not True or
                report.get("live_trading_authorized") is not False):
                result["rejected"]+=1
                continue
            digest=hashlib.sha256(json.dumps(report,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
            key=(digest,symbol)
            if key in existing:
                result["existing"]+=1
                continue
            enroll(report,symbol,destination,enrolled_at=enrolled_at)
            existing.add(key)
            result["registered"]+=1
        except (OSError,ValueError,TypeError,KeyError,RuntimeError,OverflowError):
            result["rejected"]+=1
    return result

def main():
    p=argparse.ArgumentParser(description="前向紙上研究策略登記，無實盤下單")
    p.add_argument("--state-dir",required=True)
    p.add_argument("--max-reports",type=int,default=10)
    args=p.parse_args()
    print(json.dumps(register_qualified(args.state_dir,max_reports=args.max_reports),ensure_ascii=False))

if __name__=="__main__":
    main()

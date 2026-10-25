"""Stage-five read-only batch: actual enrolled candidates -> replay -> review.

No scheduling, auto-promotion, order routing or state writes.
"""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime,timezone
from agent_forward_replay import replay
from agent_stage5_review import review_candidate

def review_enrolled(state_dir, *, now=None, limit=12):
    if type(limit) is not int or not 1<=limit<=30:
        raise ValueError("候選審查數量不合法")
    root=Path(state_dir)
    folder=root/"agent-forward"
    files=sorted(folder.glob("*.json")) if folder.is_dir() else []
    if len(files)>1000:
        raise ValueError("候選登記過多，拒絕繼續")
    results=[]
    for path in files[:limit]:
        try:
            if path.stat().st_size>8192: raise ValueError("候選檔案過大")
            entry=json.loads(path.read_text(encoding="utf-8"))
            if entry.get("schema")!="agent-forward-enrollment-v1" or entry.get("live_trading_authorized") is not False:
                raise ValueError("候選登記無效")
            digest=entry["research_sha256"]
            if not isinstance(digest,str) or len(digest)>128 or not digest.isalnum():
                raise ValueError("策略研究識別不合法")
            paper=replay(path,root/"agent-forward-observations"/digest)
            decision=review_candidate(root,paper,now=now)
            results.append({"symbol":entry["symbol"],"strategy":entry["strategy"],
                            "research_sha256":digest,"decision":decision})
        except (OSError,ValueError,TypeError,KeyError,RuntimeError):
            results.append({"symbol":"—","strategy":"—",
                            "decision":{"status":"hold_for_review","reasons":["資料無效或不足"],
                                        "automatic_promotion_authorized":False,
                                        "live_trading_authorized":False}})
    return {"schema":"agent-stage5-batch-v1","checked":len(results),
            "candidates":results,"automatic_promotion_authorized":False,
            "live_trading_authorized":False,"paper_only":True}

def save_review_snapshot(state_dir, report):
    """Content-addressed audit snapshot, no permission to promote or trade."""
    if (not isinstance(report,dict) or report.get("schema")!="agent-stage5-batch-v1"
            or report.get("automatic_promotion_authorized") is not False
            or report.get("live_trading_authorized") is not False):
        raise ValueError("不合法的策略審查報告")
    payload=json.dumps(report,ensure_ascii=False,sort_keys=True,allow_nan=False)+"\\n"
    digest=hashlib.sha256(payload.encode("utf-8")).hexdigest()
    folder=Path(state_dir)/"agent-stage5-decisions"
    folder.mkdir(parents=True,exist_ok=True)
    destination=folder/(digest+".json")
    try:
        with destination.open("x",encoding="utf-8") as out:
            out.write(payload)
    except FileExistsError:
        if destination.read_text(encoding="utf-8")!=payload:
            raise RuntimeError("策略審查紀錄指紋衝突")
    return destination

def main():
    parser=argparse.ArgumentParser(description="第五階段策略批次審查（只讀、不晉升、不下單）")
    parser.add_argument("--state-dir",required=True)
    parser.add_argument("--limit",type=int,default=12)
    parser.add_argument("--save-review",action="store_true",help="儲存不可覆寫的研究決策快照")
    args=parser.parse_args()
    report=review_enrolled(args.state_dir,limit=args.limit)
    if args.save_review:
        report["snapshot_at_utc"]=datetime.now(timezone.utc).isoformat()
        report["saved_review"]=str(save_review_snapshot(args.state_dir,report))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

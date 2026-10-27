"""Bounded read-only review of frozen B+C research candidates."""
from pathlib import Path
import json
import hashlib
from agent_forward_observation import review_frozen_candidate

def review_frozen_batch(state_dir, *, limit=3, batch_number=0):
    if (type(limit) is not int or not 1<=limit<=5 or
        type(batch_number) is not int or batch_number<0):
        raise ValueError("前向研究每輪上限無效")
    root=Path(state_dir)
    folder=root/"agent-frozen-paper-candidates"
    files=sorted(folder.glob("*.json")) if folder.is_dir() else []
    items=[]
    offset=(batch_number*limit)%len(files) if files else 0
    selected=(files+files)[offset:offset+min(limit,len(files))]
    for path in selected:
        try:
            result=review_frozen_candidate(root,path)
            if result.get("live_trading_authorized") is not False:
                raise ValueError("前向觀察權限異常")
            status=result.get("status",result.get("review",{}).get("status"))
            item={"reference_sha256":path.stem,"status":status,
                  "live_trading_authorized":False}
            if status=="review_strategy_deterioration":
                raw=path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=path.stem:
                    raise ValueError("候選基準指紋不一致")
                frozen=json.loads(raw)
                item["research_recheck"]={
                    "symbol":frozen["symbol"],
                    "interval":frozen["interval"],
                    "reason":"new_forward_paper_evidence_deteriorated",
                    "paper_only":True,"automatic_promotion_authorized":False,
                    "live_trading_authorized":False}
            items.append(item)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            items.append({"reference_sha256":path.stem,"status":"review_error",
                          "error_type":type(exc).__name__,"live_trading_authorized":False})
    return {"schema":"bc-forward-paper-batch-v1","reviewed":len(items),
            "total_frozen":len(files),"items":items,"paper_only":True,
            "automatic_promotion_authorized":False,"live_trading_authorized":False}

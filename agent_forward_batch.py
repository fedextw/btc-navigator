"""Bounded read-only review of frozen B+C research candidates."""
from pathlib import Path
from agent_forward_observation import review_frozen_candidate

def review_frozen_batch(state_dir, *, limit=3):
    if type(limit) is not int or not 1<=limit<=5:
        raise ValueError("前向研究每輪上限無效")
    root=Path(state_dir)
    folder=root/"agent-frozen-paper-candidates"
    files=sorted(folder.glob("*.json")) if folder.is_dir() else []
    items=[]
    for path in files[:limit]:
        try:
            result=review_frozen_candidate(root,path)
            if result.get("live_trading_authorized") is not False:
                raise ValueError("前向觀察權限異常")
            items.append({"reference_sha256":path.stem,
                          "status":result.get("status",result.get("review",{}).get("status")),
                          "live_trading_authorized":False})
        except (OSError,ValueError,KeyError,TypeError) as exc:
            items.append({"reference_sha256":path.stem,"status":"review_error",
                          "error_type":type(exc).__name__,"live_trading_authorized":False})
    return {"schema":"bc-forward-paper-batch-v1","reviewed":len(items),
            "total_frozen":len(files),"items":items,"paper_only":True,
            "automatic_promotion_authorized":False,"live_trading_authorized":False}

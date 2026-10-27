"""Evidence comparison for B+C deterioration-triggered research.

No claim of improvement: the new research reused observed candles, and its
heldout cannot count as a fresh independent forward test.
"""
import hashlib
import json
from pathlib import Path

def compare_research_recheck(state_dir, reference_sha256, recheck):
    if (not isinstance(reference_sha256,str) or len(reference_sha256)!=64 or
        any(c not in "0123456789abcdef" for c in reference_sha256)):
        raise ValueError("舊策略指紋不合法")
    if not isinstance(recheck,dict) or recheck.get("live_trading_authorized") is not False:
        raise ValueError("重研究結果權限不合法")
    folder=Path(state_dir)/"agent-frozen-paper-candidates"
    path=folder/(reference_sha256+".json")
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference_sha256:
        raise ValueError("舊策略基準遭到修改")
    baseline=json.loads(raw)
    if baseline.get("paper_only") is not True:
        raise ValueError("舊策略不是紙上研究")
    items=recheck.get("items",[])
    if not isinstance(items,list) or len(items)!=1:
        raise ValueError("重研究紀錄不完整")
    item=items[0]
    if item.get("symbol")!=baseline.get("symbol"):
        raise ValueError("重研究合約與原始策略不符")
    result=item.get("result",{})
    if item.get("status")!="completed" or not isinstance(result,dict):
        return {"schema":"bc-recheck-comparison-v1","status":"recheck_unavailable",
                "old_strategy":baseline.get("strategy"),
                "paper_only":True,"independent_improvement_proven":False,
                "automatic_promotion_authorized":False,"live_trading_authorized":False}
    selected=result.get("selected")
    if selected is not None and not isinstance(selected,str):
        raise ValueError("重研究選擇結果無效")
    return {"schema":"bc-recheck-comparison-v1",
            "status":"awaiting_fresh_independent_comparison",
            "old_strategy":baseline.get("strategy"),
            "new_candidate":selected,
            "same_candidate":selected==baseline.get("strategy"),
            "old_historical_cutoff_utc":baseline.get("historical_cutoff_utc"),
            "new_research_bars":result.get("bars"),
            "warning":"New candidate fitted with post-cutoff market data; cannot compare as independent forward improvement",
            "paper_only":True,"independent_improvement_proven":False,
            "automatic_promotion_authorized":False,"live_trading_authorized":False}

"""Read-only status of separately authorized OpenAI Stage 4 research."""
import json
from pathlib import Path

def load_openai_status(state_root):
    root=Path(state_root)/"stage4-openai"
    file=root/"supervisor-status.json"
    if not file.is_file():
        return {"state":"not_started","message":"OpenAI 第四階段尚未啟用（預設不產生費用）。"}
    try:
        if file.stat().st_size>65536: raise ValueError("oversize")
        x=json.loads(file.read_text(encoding="utf-8"))
        if (x.get("schema")!="agent-stage4-supervisor-status-v1" or
            x.get("paper_only") is not True or
            x.get("live_trading_authorized") is not False):
            raise ValueError("invalid provenance")
        phase=x["phase"]
        if phase not in ("running","waiting_for_fresh_data","completed",
                         "requires_manual_review","error"):
            raise ValueError("invalid phase")
        return {"state":phase,
                "message":{"running":"OpenAI 跨代研究程序正在執行",
                  "waiting_for_fresh_data":"等待新的獨立驗證資料，不會浪費模型費用",
                  "completed":"已完成本次授權研究批次",
                  "requires_manual_review":"研究中斷，需要檢查紀錄後才能繼續",
                  "error":"OpenAI 研究發生錯誤，停止付費重試"}[phase],
                "slot":str(x.get("slot",""))[:48],
                "updated_at_utc":str(x.get("updated_at_utc",""))[:40],
                "completed_batches":x.get("completed_batches",0),
                "max_model_calls_authorized":x.get("max_model_calls_authorized",0)}
    except (ValueError,KeyError,TypeError,OSError):
        return {"state":"invalid","message":"OpenAI 研究狀態資料異常，請檢查日誌。"}

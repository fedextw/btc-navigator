"""Bounded, read-only paper-forward dashboard summary.

No automatic evaluation, trades, or external requests. Failed/absent records do
not turn into positive PnL claims.
"""
import json
from pathlib import Path
from agent_forward_replay import replay

def summarize_forward(state_dir, max_enrollments=12):
    if not 1<=max_enrollments<=30:
        raise ValueError("顯示數量不合法")
    root=Path(state_dir)
    folder=root/"agent-forward"
    if not folder.is_dir():
        return {"status":"not_started","rows":[],"checked":0}
    files=sorted(folder.glob("*.json"))
    if len(files)>1000:
        return {"status":"too_many_records","rows":[],"checked":0}
    rows=[]
    for path in files[:max_enrollments]:
        try:
            if path.stat().st_size>8192: raise ValueError("登記檔太大")
            entry=json.loads(path.read_text(encoding="utf-8"))
            if entry.get("schema")!="agent-forward-enrollment-v1" or entry.get("live_trading_authorized") is not False:
                raise ValueError("非法登記")
            # Each research fingerprint gets an isolated observation directory.
            fingerprint=entry["research_sha256"]
            if not isinstance(fingerprint,str) or len(fingerprint)>128 or not fingerprint.isalnum():
                raise ValueError("研究識別不合法")
            result=replay(path,root/"agent-forward-observations"/fingerprint)
            rows.append({"合約":str(entry["symbol"])[:32],"策略":str(entry["strategy"])[:40],
                         "前向交易筆數":result.get("trades",0),
                         "可核對即時訊號筆數":result.get("prospective_eligible_trades",0),
                         "模擬淨報酬％":result.get("net_return_pct"),
                         "勝率％":result.get("win_rate_pct"),
                         "獲利因子":result.get("profit_factor"),
                         "最大回撤％":result.get("max_drawdown_pct"),
                         "驗證狀態":("等待新行情" if result.get("status")=="waiting_future_candles" else
                                   "事後讀取，非即時驗證" if result.get("evidence_status")=="retrospective_only_not_forward_verified" else
                                   "樣本不足" if result.get("evidence_status")=="needs_more_forward_samples" else
                                   "僅供進一步審核")})
        except (OSError,ValueError,TypeError,KeyError,RuntimeError,json.JSONDecodeError):
            rows.append({"合約":"—","策略":"—","前向交易筆數":0,"驗證狀態":"資料異常，未計入"})
    return {"status":"available","rows":rows,"checked":len(rows)}

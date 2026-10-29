"""Immutable evidence records for NEW, closed candles after a paper-forward enrollment.

No PnL or fills are implied by an observation. Records are content-addressed and
created exclusively; an existing record is never silently replaced.
"""
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from agent_forward_enrollment import _utc, eligible_future_candle

def record_candle(enrollment, candle, directory, observed_at=None):
    if enrollment.get("schema")!="agent-forward-enrollment-v1" or enrollment.get("live_trading_authorized") is not False:
        raise ValueError("前向研究登記不合法")
    at=_utc(candle["time"])
    observed=_utc(observed_at or datetime.now(timezone.utc).isoformat())
    if not eligible_future_candle(enrollment,at):
        raise ValueError("不能重用研究期間或登記前的歷史資料")
    # A candle is only eligible after its interval closes. Without close_time
    # there is no proof the candle was final.
    close=_utc(candle["close_time"])
    if close<=at or observed<=close:
        raise ValueError("K 棒尚未收盤或觀察時間不正確")
    values=[]
    for key in ("open","high","low","close","volume"):
        val=float(candle[key])
        if not math.isfinite(val):
            raise ValueError("K 棒數值不合法")
        values.append(val)
    o,h,l,c,v=values
    if min(o,h,l,c)<=0 or v<0 or h<max(o,c,l) or l>min(o,c,h):
        raise ValueError("OHLCV 數值不正確")
    item={"schema":"agent-forward-observation-v1",
          "research_sha256":enrollment["research_sha256"],
          "symbol":enrollment["symbol"],"strategy":enrollment["strategy"],
          "candle_time_utc":at.isoformat(),"close_time_utc":close.isoformat(),
          "observed_at_utc":observed.isoformat(),
          "ohlcv":{"open":o,"high":h,"low":l,"close":c,"volume":v},
          "status":"observed_not_traded","live_trading_authorized":False}
    data=json.dumps(item,ensure_ascii=False,sort_keys=True,allow_nan=False,indent=2)+"\n"
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    # Fixed candle identity ensures a second observation of the same bar cannot
    # be counted again, even if the observation timestamp changed.
    key="|".join((item["research_sha256"],item["symbol"],item["candle_time_utc"]))
    path=directory/(hashlib.sha256(key.encode()).hexdigest()+".json")
    try:
        with path.open("x",encoding="utf-8") as f:
            f.write(data)
    except FileExistsError:
        saved=json.loads(path.read_text(encoding="utf-8"))
        if saved.get("ohlcv")!=item["ohlcv"] or saved.get("research_sha256")!=item["research_sha256"]:
            raise RuntimeError("同一根 K 棒出現不一致資料，拒絕覆寫")
    return path

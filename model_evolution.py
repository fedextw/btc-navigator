"""Model promotion based on a common period unseen by the incumbent."""
import numpy as np
import pandas as pd
from learning_lab import feature_frame, FEATURES, predict, simulate, trade_stats


def select_model(incumbent, candidate, candles):
    if not incumbent or not incumbent["research_pass"]:
        return candidate, {"decision": "研究模型更新", "promoted": bool(candidate["research_pass"]),
                           "reason": "首次模型或原模型未達研究門檻；新模型仍需後續紙上驗證"}
    if not candidate["research_pass"]:
        return incumbent, {"decision": "保留現行模型", "promoted": False, "reason": "候選模型未通過研究門檻"}
    frame = feature_frame(candles)
    boundary = max(pd.Timestamp(incumbent["last_candle"]), pd.Timestamp(candidate["split"]["test_first_signal"]))
    indices = frame.index[frame.close_time > boundary].tolist()
    end = len(frame) - candidate["horizon"]
    if not indices or indices[0] >= end:
        return incumbent, {"decision": "保留現行模型", "promoted": False, "reason": "尚無共同且未見過的完整持有期"}
    start = indices[0]
    x = frame[FEATURES].to_numpy()
    outcomes = {}
    for label, model in (("incumbent", incumbent), ("candidate", candidate)):
        trades = simulate(frame, predict(model["model"], x), start, end,
                          candidate["horizon"], model["threshold"], candidate["cost"])
        outcomes[label] = trade_stats(trades)
    old, new = outcomes["incumbent"], outcomes["candidate"]
    enough = min(old["trades"], new["trades"]) >= 20
    better = bool(enough and new["expectancy_pct"] > old["expectancy_pct"] and
                  new["net_pct"] > old["net_pct"] and new["max_drawdown_pct"] <= old["max_drawdown_pct"])
    audit = {"decision": "晉升候選模型" if better else "保留現行模型", "promoted": better,
             "reason": "共同未見期間的報酬與回撤較佳" if better else "共同樣本不足 20 筆或報酬／回撤沒有一起改善",
             "period_start": str(frame.iloc[start].close_time), "period_end": str(frame.iloc[end - 1].close_time),
             "comparison": outcomes, "incumbent_id": incumbent["id"], "candidate_id": candidate["id"]}
    return (candidate if better else incumbent), audit

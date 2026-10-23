"""Conservative agreement gate. Agreement is research evidence, never a win guarantee."""
from datetime import datetime, timezone
import pandas as pd
from learning_lab import current_prediction


def consensus(market, analysis, record=None):
    gates = {"真實行情": market["mode"] == "live", "行情完整且未過期": analysis["valid"],
             "已有模型": record is not None}
    prediction = None
    if record:
        trained = pd.Timestamp(record["trained_at"])
        now = pd.Timestamp(datetime.now(timezone.utc))
        gates["模型通過研究門檻"] = record["research_pass"] and not record["demo"]
        gates["模型未超過七天"] = 0 <= (now - trained).total_seconds() <= 7 * 86400
        gates["行情已超出訓練視窗"] = market["candles"].iloc[-1].close_time > pd.Timestamp(record["last_candle"])
        prediction = current_prediction(record, market["candles"])
        gates["規則與模型方向一致"] = prediction["side"] == analysis["side"] and prediction["side"] != "WAIT"
    side = analysis["side"] if all(gates.values()) else "WAIT"
    return {"side": side, "gates": gates, "model_probability": prediction["probability"] if prediction else None,
            "model_side": prediction["side"] if prediction else None, "rule_side": analysis["side"],
            "label": "研究共識，未經實盤驗證"}

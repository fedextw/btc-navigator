"""Explainable research heuristics, not a trained predictive model or backtest."""
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from market_data import INTERVALS


def indicators(candles):
    frame = candles.copy()
    close = frame.close
    for period in (20, 50, 200):
        frame[f"ema{period}"] = close.ewm(span=period, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    frame["rsi"] = (100 - 100 / (1 + rs)).where(loss != 0, 100).where((gain != 0) | (loss != 0), 50)
    previous = close.shift()
    true_range = pd.concat([frame.high - frame.low, (frame.high - previous).abs(),
                            (frame.low - previous).abs()], axis=1).max(axis=1)
    frame["atr"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    frame["macd"] = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    frame["macd_signal"] = frame.macd.ewm(span=9, adjust=False).mean()
    frame["macd_hist"] = frame.macd - frame.macd_signal
    frame["volume_ratio"] = frame.volume / frame.volume.rolling(20).mean().replace(0, np.nan)
    return frame


def market_structure(frame):
    last = frame.iloc[-1]
    prior = frame.iloc[-21:-1]
    high, low = float(prior.high.max()), float(prior.low.min())
    bos = "看多突破" if last.close > high else "看空跌破" if last.close < low else "區間內整理"
    sweep = "掃過上方流動性後收回" if last.high > high and last.close < high else (
        "掃過下方流動性後收回" if last.low < low and last.close > low else "未偵測到掃單")
    # A three-candle imbalance; keep the most recent gap which has not been fully filled.
    gaps = []
    for i in range(max(2, len(frame) - 60), len(frame)):
        a, c = frame.iloc[i - 2], frame.iloc[i]
        tail = frame.iloc[i + 1:]
        if c.low > a.high and (tail.empty or tail.low.min() > a.high):
            gaps.append(dict(kind="Bullish FVG", low=float(a.high), high=float(c.low), time=c.time))
        elif c.high < a.low and (tail.empty or tail.high.max() < a.low):
            gaps.append(dict(kind="Bearish FVG", low=float(c.high), high=float(a.low), time=c.time))
    midpoint = (high + low) / 2
    zone = "Premium 溢價區" if last.close > midpoint else "Discount 折價區"
    return dict(high=high, low=low, midpoint=midpoint, bos=bos, sweep=sweep, gaps=gaps[-3:], zone=zone)


def analyze(market, now=None):
    frame = indicators(market["candles"])
    row = frame.iloc[-1]
    structure = market_structure(frame)
    factors = []
    def add(name, score, evidence):
        factors.append(dict(name=name, score=score, evidence=evidence))
    trend = 2 if row.ema20 > row.ema50 > row.ema200 else -2 if row.ema20 < row.ema50 < row.ema200 else 0
    add("趨勢排列", trend, "EMA 20 / 50 / 200 多頭排列" if trend > 0 else "EMA 20 / 50 / 200 空頭排列" if trend < 0 else "均線排列分歧")
    momentum = 1 if 50 < row.rsi < 70 else -1 if 30 < row.rsi < 50 else 0
    add("RSI 動能", momentum, f"RSI(14) {row.rsi:.1f}；超買超賣不直接視為反轉")
    add("MACD", 1 if row.macd_hist > 0 else -1 if row.macd_hist < 0 else 0, f"柱體 {row.macd_hist:.4f}")
    add("市場結構", 2 if structure["bos"] == "看多突破" else -2 if structure["bos"] == "看空跌破" else 0, structure["bos"] + "（前 20 根高低點）")
    add("流動性掃單", 1 if "下方" in structure["sweep"] else -1 if "上方" in structure["sweep"] else 0, structure["sweep"])
    funding = market.get("funding")
    add("擁擠風險", -1 if funding is not None and funding > 0.05 else 1 if funding is not None and funding < -0.05 else 0,
        "費率資料不可用，排除" if funding is None else f"當期費率 {funding:+.4f}%；極端費率採逆向風險權重")
    oi = market.get("oi_change")
    add("持倉參與", 0, "OI 不可用，排除" if oi is None else f"近 30 個樣本 OI {oi:+.2f}%；OI 無法單獨判定多空，僅供觀察")
    if "taker_buy_quote" in frame:
        delta = (2 * frame.taker_buy_quote.tail(20) - frame.quote_volume.tail(20)).sum()
        add("主動成交差額", 0, f"近 20 根主動買入減賣出 {delta / 1e6:+.2f}M USDT；成交差額不等同淨資金流入")
    score = sum(f["score"] for f in factors)
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    seconds = INTERVALS[market["interval"]]
    age = (now - row.close_time).total_seconds()
    diffs = frame.time.diff().dropna().dt.total_seconds()
    valid = bool(0 <= age <= seconds * 1.5 and (diffs == seconds).all() and
                 np.isfinite([row.atr, row.rsi, row.close]).all() and row.atr > 0)
    side = "LONG" if score >= 4 else "SHORT" if score <= -4 else "WAIT"
    reasons = []
    if not valid:
        side = "WAIT"
        reasons.append("行情過期、時間不連續或指標不足，停止產生方向訊號")
    if abs(score) < 4:
        reasons.append("多空條件未達門檻（需 |分數| ≥ 4）")
    if market["mode"] == "demo":
        reasons.append("示範行情：此處僅展示計算結果，不是即時交易訊號")
    entry = float(row.close)
    distance = float(row.atr) * 1.8
    if distance >= entry:
        side = "WAIT"
        reasons.append("ATR 停損距離過大，停止產生研究價位")
    direction = 1 if side == "LONG" else -1
    stop = entry - direction * distance if side != "WAIT" else None
    targets = [entry + direction * distance * rr for rr in (1.5, 2, 3)] if side != "WAIT" else []
    return dict(frame=frame, structure=structure, factors=factors, score=score, side=side,
                entry=entry, stop=stop, targets=targets, valid=valid, reasons=reasons,
                distance=distance, alignment=round(abs(score) / 8 * 100), age=age)


def position_size(equity, risk_pct, entry, stop, leverage=1, fee_pct=0.05):
    values = [equity, risk_pct, entry, stop, leverage, fee_pct]
    if not np.isfinite(values).all() or equity <= 0 or entry <= 0 or stop <= 0 or entry == stop:
        raise ValueError("資金、價格與停損距離必須有效")
    if not 0 < risk_pct <= 5 or not 1 <= leverage <= 50 or not 0 <= fee_pct <= 1:
        raise ValueError("風險、槓桿或費率超出範圍")
    budget = equity * risk_pct / 100
    unit_risk = abs(entry - stop) + (entry + stop) * fee_pct / 100
    quantity = budget / unit_risk
    notional = quantity * entry
    return dict(quantity=quantity, notional=notional, margin=notional / leverage,
                budget=budget, exceeds_equity=notional / leverage > equity)

"""Small, auditable ML baseline and strictly chronological trading simulation.

No fitted model sees test observations. No news or current funding is backfilled.
Models are local JSON records; no untrusted pickle deserialization.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import sqlite3

import numpy as np
import pandas as pd

from analysis_engine import indicators

FEATURES = ["ret1", "ret3", "ret12", "ema_gap", "ema200_gap", "rsi_scaled", "macd_scaled", "atr_scaled", "volume_scaled"]
MODEL_VERSION = 1


def feature_frame(candles):
    frame = indicators(candles)
    close = frame.close
    frame["ret1"] = close.pct_change()
    frame["ret3"] = close.pct_change(3)
    frame["ret12"] = close.pct_change(12)
    frame["ema_gap"] = (frame.ema20 - frame.ema50) / close
    frame["ema200_gap"] = (close - frame.ema200) / close
    frame["rsi_scaled"] = (frame.rsi - 50) / 50
    frame["macd_scaled"] = frame.macd_hist / close
    frame["atr_scaled"] = frame.atr / close
    frame["volume_scaled"] = frame.volume_ratio - 1
    frame = frame.iloc[200:].replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURES)
    return frame.reset_index(drop=True)


def sigmoid(values):
    return 1 / (1 + np.exp(-np.clip(values, -35, 35)))


def fit_classifier(x, y, regularization):
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale = np.where(scale < 1e-9, 1, scale)
    z = np.clip((x - mean) / scale, -10, 10)
    weights = np.zeros(x.shape[1])
    bias = 0.0
    for _ in range(450):
        error = sigmoid(z @ weights + bias) - y
        weights -= 0.08 * (z.T @ error / len(y) + regularization * weights)
        bias -= 0.08 * error.mean()
    return dict(mean=mean.tolist(), scale=scale.tolist(), weights=weights.tolist(), bias=float(bias))


def predict(model, x):
    z = np.clip((np.asarray(x) - np.array(model["mean"])) / np.array(model["scale"]), -10, 10)
    return sigmoid(z @ np.array(model["weights"]) + model["bias"])


def simulate(frame, probabilities, start, end, horizon, threshold, cost):
    trades = []
    next_signal_index = start
    for index in range(start, min(end, len(frame) - horizon)):
        if index < next_signal_index:
            continue
        probability = float(probabilities[index])
        side = 1 if probability >= threshold else -1 if probability <= 1 - threshold else 0
        if side == 0:
            continue
        # Features at i's close, enter at i+1 open, exit at i+h close.
        entry = float(frame.iloc[index + 1].open)
        exit_price = float(frame.iloc[index + horizon].close)
        net = side * (exit_price / entry - 1) - cost
        trades.append(dict(signal_time=str(frame.iloc[index].close_time),
                           entry_time=str(frame.iloc[index + 1].time),
                           exit_time=str(frame.iloc[index + horizon].close_time),
                           side="LONG" if side > 0 else "SHORT", probability=probability,
                           entry=entry, exit=exit_price, net_return=net))
        next_signal_index = index + horizon
    return trades


def trade_stats(trades):
    returns = np.array([t["net_return"] for t in trades], dtype=float)
    if not len(returns):
        return dict(trades=0, win_rate=None, net_pct=0.0, max_drawdown_pct=0.0,
                    profit_factor=None, expectancy_pct=None, curve=[1.0])
    curve = np.r_[1.0, np.cumprod(1 + returns)]
    drawdown = curve / np.maximum.accumulate(curve) - 1
    losses = -returns[returns < 0].sum()
    return dict(trades=len(returns), win_rate=float((returns > 0).mean() * 100),
                net_pct=float((curve[-1] - 1) * 100), max_drawdown_pct=float(-drawdown.min() * 100),
                profit_factor=float(returns[returns > 0].sum() / losses) if losses > 0 else None,
                expectancy_pct=float(returns.mean() * 100), curve=curve.tolist())


def train_and_evaluate(candles, symbol, interval, demo=False, horizon=6, fee_pct=0.05, slippage_pct=0.02):
    if horizon not in (3, 6, 12) or not 0 <= fee_pct <= 1 or not 0 <= slippage_pct <= 1:
        raise ValueError("訓練參數不正確")
    raw = candles.copy()
    if len(raw) < 800:
        raise ValueError("至少需要 800 根已收盤 K 線")
    seconds = {"15m": 900, "1h": 3600, "4h": 14400}[interval]
    if not (raw.time.diff().dropna().dt.total_seconds() == seconds).all():
        raise ValueError("歷史 K 線不連續，不能進行回測")
    frame = feature_frame(raw)
    n = len(frame)
    train_end, val_end = int(n * .6), int(n * .8)
    x = frame[FEATURES].to_numpy(dtype=float)
    future_return = frame.close.shift(-horizon) / frame.open.shift(-1) - 1
    y = (future_return > 0).astype(float).to_numpy()
    cost = 2 * (fee_pct + slippage_pct) / 100
    # Purge labels at partition boundaries: a training outcome never enters validation.
    train_stop = train_end - horizon
    val_stop = val_end - horizon
    best = None
    candidates = []
    for regularization in (0.001, 0.01, 0.1):
        model = fit_classifier(x[:train_stop], y[:train_stop], regularization)
        probabilities = predict(model, x)
        for threshold in (.55, .60, .65):
            trades = simulate(frame, probabilities, train_end, val_stop, horizon, threshold, cost)
            stats = trade_stats(trades)
            # Select on validation only. Reject tiny sample sizes for tuning.
            merit = stats["net_pct"] - .5 * stats["max_drawdown_pct"] if stats["trades"] >= 5 else -1e9
            candidates.append(dict(regularization=regularization, threshold=threshold,
                                   validation_trades=stats["trades"], validation_net_pct=stats["net_pct"]))
            if best is None or merit > best[0]:
                best = (merit, model, threshold, regularization, stats)
    _, model, threshold, regularization, validation_stats = best
    probabilities = predict(model, x)
    test_stop = n - horizon
    trades = simulate(frame, probabilities, val_end, test_stop, horizon, threshold, cost)
    stats = trade_stats(trades)
    test_y = y[val_end:test_stop]
    test_probabilities = probabilities[val_end:test_stop]
    brier = float(np.mean((test_probabilities - test_y) ** 2))
    baseline_p = float(y[:train_stop].mean())
    baseline_brier = float(np.mean((baseline_p - test_y) ** 2))
    checks = {
        "測試交易至少 20 筆": stats["trades"] >= 20,
        "扣成本後期望值為正": stats["expectancy_pct"] is not None and stats["expectancy_pct"] > 0,
        "Profit factor 至少 1.1": stats["profit_factor"] is not None and stats["profit_factor"] >= 1.1,
        "測試回撤小於 15%": stats["max_drawdown_pct"] < 15,
        "機率誤差優於固定比例基準": brier < baseline_brier,
        "使用真實行情": not demo,
        "驗證集足夠交易": validation_stats["trades"] >= 5,
    }
    dataset_sha256 = hashlib.sha256(raw.to_csv(index=False).encode()).hexdigest()
    identity = hashlib.sha256((symbol + interval + dataset_sha256 + str(horizon) + str(cost) + str(demo) + str(MODEL_VERSION)).encode()).hexdigest()[:16]
    return dict(version=MODEL_VERSION, id=identity, symbol=symbol, interval=interval, demo=demo,
                trained_at=datetime.now(timezone.utc).isoformat(), last_candle=str(raw.iloc[-1].close_time),
                model=model, threshold=threshold, regularization=regularization, horizon=horizon,
                cost=cost, fee_pct=fee_pct, slippage_pct=slippage_pct,
                features=FEATURES, test_stats=stats, validation_stats=validation_stats,
                brier=brier, baseline_brier=baseline_brier, checks=checks, research_pass=all(checks.values()),
                split={"train": train_stop, "validation": val_stop - train_end, "test": test_stop - val_end,
                       "train_last_outcome": str(frame.iloc[train_stop - 1 + horizon].close_time),
                       "validation_first_signal": str(frame.iloc[train_end].close_time),
                       "validation_last_outcome": str(frame.iloc[val_stop - 1 + horizon].close_time),
                       "test_first_signal": str(frame.iloc[val_end].close_time)},
                trades=trades, candidates=candidates,
                train_majority_probability=baseline_p,
                dataset_sha256=dataset_sha256,
                historical_range=[str(raw.iloc[0].time), str(raw.iloc[-1].close_time)])


def model_path(root, symbol, interval, demo):
    # Caller uses a fixed root and whitelisted exchange symbols/timeframes.
    from market_data import valid_symbol, INTERVALS
    if not valid_symbol(symbol) or interval not in INTERVALS:
        raise ValueError("模型路徑參數不正確")
    return Path(root) / f'{symbol}-{interval}-{"demo" if demo else "live"}.json'


def save_record(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as stream:
        temporary = stream.name
        stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False))
    try:
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_record(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def current_prediction(record, candles):
    frame = feature_frame(candles)
    probability = float(predict(record["model"], frame[FEATURES].iloc[[-1]].to_numpy())[0])
    side = "LONG" if probability >= record["threshold"] else "SHORT" if probability <= 1 - record["threshold"] else "WAIT"
    # A holdout pass is still only permission for further paper observation.
    return dict(probability=probability, side=side, paper_only=True)


def update_paper_journal(path, record, candles):
    """Persist forecasts before outcomes exist; fill on NEXT bar, never signal close."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path.parent / "journal-lock.sqlite3", timeout=15) as lock:
        lock.execute("BEGIN IMMEDIATE")
        return _update_paper_journal(path, record, candles)


def _update_paper_journal(path, record, candles):
    journal = load_record(path) or {"version": 1, "rows": []}
    processing_key = record["id"] + "/" + str(candles.iloc[-1].close_time)
    if journal.get("last_processing_key") == processing_key:
        return journal
    # A retrain must not discard or rewrite forecasts from older model versions.
    rows = journal["rows"]
    for row in rows:
        if row["status"] != "pending":
            continue
        future = candles[candles.time > pd.Timestamp(row["signal_time"])]
        if not future.empty and (future.iloc[0].time - pd.Timestamp(row["signal_time"])).total_seconds() > .01:
            row["status"] = "unresolved"
            row["reason"] = "下一根 K 線已不在資料視窗內；不補造進場或績效"
            continue
        if not future.empty and row.get("entry") is None:
            row["entry"] = float(future.iloc[0].open)
            row["entry_time"] = str(future.iloc[0].time)
        if len(future) >= row["horizon"] and row.get("entry") is not None:
            exit_bar = future.iloc[row["horizon"] - 1]
            direction = 1 if row["side"] == "LONG" else -1
            row.update(status="closed", exit=float(exit_bar.close), exit_time=str(exit_bar.close_time),
                       net_return=direction * (float(exit_bar.close) / row["entry"] - 1) - row["cost"])
    last = candles.iloc[-1]
    # Do not allow the training window's own last bar into forward validation.
    if last.close_time > pd.Timestamp(record["last_candle"]):
        prediction = current_prediction(record, candles)
        key = str(last.close_time)
        if prediction["side"] != "WAIT" and not any(r["status"] == "pending" for r in rows) and not any(r["signal_time"] == key for r in rows):
            rows.append(dict(signal_time=key, model_id=record["id"], side=prediction["side"],
                             probability=prediction["probability"], horizon=record["horizon"], cost=record["cost"],
                             status="pending", entry=None, demo=record["demo"]))
    closed = [row for row in rows if row["status"] == "closed"]
    journal["summary"] = {"trades": len(closed), "wins": sum(row["net_return"] > 0 for row in closed),
        "sum_net_returns": sum(row["net_return"] for row in closed),
        "gross_profit": sum(max(row["net_return"], 0) for row in closed),
        "gross_loss": -sum(min(row["net_return"], 0) for row in closed),
        "pending": sum(row["status"] == "pending" for row in rows),
        "unresolved": sum(row["status"] == "unresolved" for row in rows)}
    journal["last_processing_key"] = processing_key
    save_record(path, journal)
    return journal

"""Continuous public-data collection, scheduled retraining, and paper observation.

Run one instance per symbol/interval. No account access or order placement.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
import pandas as pd

from analysis_engine import analyze
from learning_lab import (load_record, model_path, save_record, train_and_evaluate,
                          update_paper_journal)
from market_data import SYMBOLS, INTERVALS, demo_market, live_market, load_history, load_news
from runtime_config import STATE_ROOT
from context_data import load_context



def connect(root=STATE_ROOT):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / "research.sqlite3", timeout=15)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS heartbeat (
      name TEXT PRIMARY KEY, updated_at TEXT, status TEXT, detail TEXT);
    CREATE TABLE IF NOT EXISTS snapshots (
      id INTEGER PRIMARY KEY, observed_at TEXT, symbol TEXT, interval TEXT, mode TEXT,
      candle_time TEXT, price REAL, funding REAL, oi_usd REAL, oi_change REAL, rule_side TEXT, score INTEGER);
    CREATE TABLE IF NOT EXISTS news (
      url TEXT PRIMARY KEY, title TEXT, source TEXT, published TEXT, first_observed_at TEXT);
    CREATE TABLE IF NOT EXISTS training_runs (
      id TEXT PRIMARY KEY, observed_at TEXT, symbol TEXT, interval TEXT, mode TEXT,
      research_pass INTEGER, report TEXT);
    CREATE TABLE IF NOT EXISTS candles (
      symbol TEXT, interval TEXT, mode TEXT, time TEXT, close_time TEXT,
      open REAL, high REAL, low REAL, close REAL, volume REAL,
      PRIMARY KEY(symbol, interval, mode, time));
    CREATE TABLE IF NOT EXISTS market_context (
      observed_at TEXT PRIMARY KEY, payload TEXT);
    """)
    return db


def store_candles(db, frame, symbol, interval, mode):
    db.executemany("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?)", [
        (symbol, interval, mode, row.time.isoformat(), row.close_time.isoformat(),
         float(row.open), float(row.high), float(row.low), float(row.close), float(row.volume))
        for row in frame.itertuples()])
    db.commit()


def accumulated_history(db, symbol, interval, mode):
    frame = pd.read_sql_query("SELECT time,close_time,open,high,low,close,volume FROM candles WHERE symbol=? AND interval=? AND mode=? ORDER BY time DESC LIMIT 5000",
        db, params=(symbol, interval, mode)).iloc[::-1].reset_index(drop=True)
    frame["time"] = pd.to_datetime(frame.time, utc=True)
    frame["close_time"] = pd.to_datetime(frame.close_time, utc=True)
    breaks = frame.time.diff().dt.total_seconds().dropna() != INTERVALS[interval]
    if breaks.any():
        frame = frame.iloc[int(breaks[breaks].index[-1]):].reset_index(drop=True)
    return frame


def heartbeat(db, name, status, detail):
    db.execute("INSERT OR REPLACE INTO heartbeat VALUES (?, ?, ?, ?)",
               (name, datetime.now(timezone.utc).isoformat(), status, detail))
    db.commit()


def external_cycle(db, stamp):
    errors = []
    for category, delay in (("news", 300), ("context", 900)):
        previous = db.execute("SELECT updated_at FROM heartbeat WHERE name=?", (category,)).fetchone()
        if previous and (datetime.now(timezone.utc) - datetime.fromisoformat(previous[0])).total_seconds() < delay:
            continue
        if category == "news":
            articles, failures = load_news()
            for article in articles:
                db.execute("INSERT OR IGNORE INTO news VALUES (?,?,?,?,?)",
                    (article["url"], article["title"], article["source"], article["published"], stamp))
            errors.extend(failures)
            heartbeat(db, "news", "partial" if failures else "ok", "、".join(failures) or f"已收集 {len(articles)} 則")
        else:
            context = load_context()
            db.execute("INSERT OR REPLACE INTO market_context VALUES (?,?)", (stamp, json.dumps(context, ensure_ascii=False)))
            errors.extend(context["errors"])
            heartbeat(db, "context", "partial" if context["errors"] else "ok", "、".join(context["errors"]) or "全球市場背景已更新")
    return errors


def collect_cycle(symbol="BTCUSDT", interval="1h", demo=False, train=False, root=STATE_ROOT, news=True):
    root = Path(root)
    db = connect(root)
    name = f'{symbol}/{interval}/{"demo" if demo else "live"}'
    stamp = datetime.now(timezone.utc).isoformat()
    try:
        heartbeat(db, name, "collecting", "正在讀取公開資料")
        # A failed exchange must not stop independent news/context collection.
        news_errors = external_cycle(db, stamp) if news and not demo else []
        # Never silently switch a live worker to synthetic data.
        market = demo_market(symbol, interval) if demo else live_market(symbol, interval)
        store_candles(db, market["candles"], symbol, interval, market["mode"])
        result = analyze(market)
        db.execute("INSERT INTO snapshots (observed_at,symbol,interval,mode,candle_time,price,funding,oi_usd,oi_change,rule_side,score) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (stamp, symbol, interval, market["mode"], str(market["candles"].iloc[-1].close_time),
                    result["entry"], market["funding"], market["oi_usd"], market["oi_change"], result["side"], result["score"]))
        db.commit()
        path = model_path(root / "models", symbol, interval, demo)
        record = load_record(path)
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(record["trained_at"])).total_seconds() if record else float("inf")
        latest = market["candles"].iloc[-1].close_time
        new_bars = (latest - pd.Timestamp(record["last_candle"])).total_seconds() / INTERVALS[interval] if record else float("inf")
        if train and elapsed >= 86400 and new_bars >= 24 and result["valid"]:
            candles = load_history(symbol, interval, demo)
            store_candles(db, candles, symbol, interval, market["mode"])
            candles = accumulated_history(db, symbol, interval, market["mode"])
            new_record = train_and_evaluate(candles, symbol, interval, demo,
                horizon=record["horizon"] if record else 6,
                fee_pct=record.get("fee_pct", .05) if record else .05,
                slippage_pct=record.get("slippage_pct", .02) if record else .02)
            new_record["input_source"] = "demo" if demo else "binance"
            dataset = root / "datasets" / f'{new_record["id"]}.csv'
            dataset.parent.mkdir(parents=True, exist_ok=True)
            candles.to_csv(dataset, index=False)
            save_record(root / "models" / "archive" / f'{new_record["id"]}.json', new_record)
            save_record(path, new_record)
            record = new_record
            db.execute("INSERT OR IGNORE INTO training_runs VALUES (?,?,?,?,?,?,?)",
                       (record["id"], stamp, symbol, interval, market["mode"], int(record["research_pass"]), json.dumps(record, ensure_ascii=False)))
            db.commit()
        if record and result["valid"]:
            update_paper_journal(model_path(root / "paper", symbol, interval, demo), record, market["candles"])
        status = "ok" if result["valid"] and not market["errors"] and not news_errors else "partial"
        detail = "公開行情已記錄；" + ("合成示範" if demo else "即時來源") + ("；新聞來源部分不可用" if news_errors else "")
        if not result["valid"]:
            detail += "；K 線檢驗未通過，不新增紙上訊號"
        heartbeat(db, name, status, detail)
        return dict(status=status, symbol=symbol, interval=interval, mode=market["mode"], model_id=record["id"] if record else None)
    except Exception as exc:
        # Log exception type only: upstream request strings can contain credentials.
        heartbeat(db, name, "error", f"資料收集失敗：{type(exc).__name__}；沒有回退為示範行情")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="BTC Navigator 持續研究程序（僅紙上觀察）")
    parser.add_argument("--symbol", choices=SYMBOLS, default="BTCUSDT")
    parser.add_argument("--interval", choices=INTERVALS, default="1h")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--train", action="store_true", help="每至少 24 小時且至少 24 根新 K 線重訓")
    parser.add_argument("--demo", action="store_true", help="合成資料，與真實紀錄隔離")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.seconds < 30:
        parser.error("輪詢間隔至少 30 秒")
    while True:
        try:
            print(json.dumps(collect_cycle(args.symbol, args.interval, args.demo, args.train), ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"status": "error", "error_type": type(exc).__name__}), flush=True)
            if args.once:
                raise SystemExit(1)
        if args.once:
            break
        time.sleep(args.seconds)


if __name__ == "__main__":
    main()

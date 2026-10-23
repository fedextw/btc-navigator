"""Discover and scan all active Binance USDT perpetuals; publish research signals only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import signal
import threading
import time

import pandas as pd

from analysis_engine import analyze
from binance_client import BinanceClient, RatePause, BinanceAccessError
from collector import connect as research_db, store_candles, accumulated_history, external_cycle
from decision_engine import consensus
from learning_lab import (model_path, load_record, save_record, train_and_evaluate, update_paper_journal)
from market_data import SYMBOLS, INTERVALS, active_usdt_contracts, validate_candles, demo_market
from monitor_settings import load_settings
from notifications import dispatch
from runtime_config import STATE_ROOT
from signal_store import connect, set_state, get_state, save_result, record_signal
from model_evolution import select_model
from market_regime import classify
from multi_timeframe import compare as compare_periods


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def numeric(value, positive=False):
    try:
        result = float(value)
        return result if math.isfinite(result) and (not positive or result > 0) else None
    except (TypeError, ValueError):
        return None


class MarketScanner:
    def __init__(self, root=STATE_ROOT, client=None, demo=False):
        self.root, self.client, self.demo = Path(root), client or BinanceClient(), demo

    def universe(self, db):
        if self.demo:
            return list(SYMBOLS)
        cached = get_state(db, "universe")
        if cached and time.time() - cached["fetched_at"] < 300:
            return cached["symbols"]
        info = self.client.json("/fapi/v1/exchangeInfo", weight=1)
        symbols = active_usdt_contracts(info)
        for rule in info.get("rateLimits", []):
            if rule.get("rateLimitType") == "REQUEST_WEIGHT" and rule.get("interval") == "MINUTE":
                self.client.budget.limit = max(20, int(rule["limit"] * .6))
        set_state(db, "universe", {"symbols": symbols, "fetched_at": time.time()})
        active = set(symbols)
        for row in db.execute("SELECT symbol,interval,mode FROM scan_results").fetchall():
            if row["mode"] == "live" and row["symbol"] not in active:
                db.execute("DELETE FROM scan_results WHERE symbol=? AND interval=? AND mode=?", tuple(row))
        for row in db.execute("SELECT id,symbol FROM events WHERE expires_at>?", (time.time(),)).fetchall():
            if row["symbol"] not in active:
                db.execute("UPDATE events SET expires_at=? WHERE id=?", (time.time(), row["id"]))
        db.commit()
        return symbols

    def batch_context(self, db):
        if self.demo:
            return {}, {}
        premium = self.client.json("/fapi/v1/premiumIndex", weight=10)
        if not isinstance(premium, list):
            raise ValueError("標記價格資料格式異常")
        marks = {r["symbol"]: r for r in premium if isinstance(r, dict) and "symbol" in r}
        cached = get_state(db, "tickers")
        if not cached or time.time() - cached["fetched_at"] >= 300:
            rows = self.client.json("/fapi/v1/ticker/24hr", weight=40)
            if not isinstance(rows, list):
                raise ValueError("24 小時成交額資料格式異常")
            cached = {"rows": {r["symbol"]: r for r in rows if isinstance(r, dict) and "symbol" in r}, "fetched_at": time.time()}
            set_state(db, "tickers", cached)
        return marks, cached["rows"]

    def frame_from_cache(self, db, symbol, interval):
        mode = "demo" if self.demo else "live"
        row = db.execute("SELECT payload FROM scan_cache WHERE symbol=? AND interval=? AND mode=?", (symbol, interval, mode)).fetchone()
        if not row:
            return None
        frame = pd.DataFrame(json.loads(row[0]))
        frame["time"] = pd.to_datetime(frame.time, utc=True)
        frame["close_time"] = pd.to_datetime(frame.close_time, utc=True)
        # Wait a few seconds for the exchange to finalize the new closed candle.
        expected = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(seconds=5)).floor(f'{INTERVALS[interval]}s') - pd.Timedelta(milliseconds=1)
        return frame if frame.iloc[-1].close_time >= expected else None

    def fetch_frame(self, symbol, interval):
        if self.demo:
            return demo_market(symbol, interval)["candles"]
        rows = self.client.json("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": 300}, weight=2)
        return validate_candles(rows)

    def market(self, symbol, interval, frame, marks):
        if self.demo:
            result = demo_market(symbol, interval)
            result["candles"] = frame
            return result
        mark = marks.get(symbol, {})
        stamp = numeric(mark.get("time"))
        fresh = stamp is not None and abs(time.time() - stamp / 1000) < 180
        funding = numeric(mark.get("lastFundingRate")) if fresh else None
        return {"symbol": symbol, "interval": interval, "candles": frame, "mode": "live",
                "funding": funding * 100 if funding is not None else None, "mark_time": stamp / 1000 if fresh else None,
                "mark_price": numeric(mark.get("markPrice"), positive=True) if fresh else None,
                "oi_usd": None, "oi_change": None, "errors": {}, "fetched_at": datetime.now(timezone.utc)}

    def evaluate(self, db, market, ticker, settings):
        symbol, interval = market["symbol"], market["interval"]
        result = analyze(market)
        record = load_record(model_path(self.root / "models", symbol, interval, self.demo))
        decision = consensus(market, result, record)
        volume = numeric(ticker.get("quoteVolume")) if not self.demo else 1e9
        gates = decision["gates"]
        gates["成交額達設定門檻"] = volume is not None and volume >= settings["min_volume_usdt"]
        mark = market["mark_price"]
        gates["標記價格新鮮且未過度偏離"] = mark is not None and abs(mark - result["entry"]) <= float(result["frame"].iloc[-1].atr) * .75
        if not all(gates.values()):
            decision["side"] = "WAIT"
        reasons = ["未符合：" + name for name, value in gates.items() if not value]
        paper_summary = {}
        if record and result["valid"]:
            journal = update_paper_journal(model_path(self.root / "paper", symbol, interval, self.demo), record, market["candles"])
            paper_summary = journal.get("summary", {})
            db.execute("INSERT OR REPLACE INTO paper_metrics VALUES (?,?,?,?)",
                (symbol, interval, market["mode"], json.dumps(paper_summary)))
        row = {"symbol": symbol, "interval": interval, "mode": market["mode"], "updated_at": utcnow(),
            "side": decision["side"], "rule_side": result["side"], "model_side": decision["model_side"],
            "score": result["score"], "price": result["entry"], "mark_price": mark,
            "model_probability": decision["model_probability"], "volume_24h": volume, "mark_time": market.get("mark_time"),
            "model_id": record["id"] if record else None, "model_pass": bool(record and record["research_pass"]),
            "reasons": reasons, "candle_time": str(market["candles"].iloc[-1].close_time),
            "gates": gates, "paper_summary": paper_summary,
            "regime": classify(market["candles"]),
            "walk_evidence_pass": bool(record and record.get("walk_forward", {}).get("evidence_pass")),
            "status": "方向成立" if decision["side"] != "WAIT" else "待訓練" if record is None else "觀望"}
        save_result(db, row)
        if decision["side"] != "WAIT":
            expiration = min(time.time() + INTERVALS[interval], market["candles"].iloc[-1].close_time.timestamp() + INTERVALS[interval])
            payload = {**row, "entry": result["entry"], "stop": result["stop"], "targets": result["targets"],
                "factors": result["factors"], "expires_at": expiration, "news": self.relevant_news(symbol)}
            record_signal(db, payload, settings["cooldown_minutes"])
        return row, result, record

    def collect_qualified_shadow(self, db, interval, mode, marks, status):
        # Skip completed or recently attempted symbols so the first two do not
        # starve the rest of the qualified universe on subsequent cycles.
        rows = db.execute("SELECT symbol,payload FROM scan_results WHERE interval=? AND mode=? AND side!='WAIT' ORDER BY updated_at DESC,symbol", (interval, mode)).fetchall()
        attempts = 0
        for row in rows:
            result = json.loads(row["payload"])
            key = f'research/{row["symbol"]}/{interval}/{mode}'
            previous = get_state(db, key, {})
            same = previous.get("as_of") == result.get("candle_time")
            if same and previous.get("complete"):
                continue
            if time.time() - previous.get("attempted_at", 0) < 600:
                continue
            set_state(db, key, {**previous, "attempted_at": time.time()})
            try:
                self.collect_shadow(db, row["symbol"], interval, marks)
            except Exception as exc:
                db.rollback()
                status["errors"].append(f'{row["symbol"]} 影子研究暫不可用：{type(exc).__name__}')
            attempts += 1
            if attempts >= 2:
                break

    def collect_shadow(self, db, symbol, interval, marks):
        """At most two qualified symbols per cycle; primary delivery never waits."""
        mode = "demo" if self.demo else "live"
        markets = {}
        errors = []
        reference = self.frame_from_cache(db, symbol, interval)
        if reference is None:
            return
        as_of = reference.iloc[-1].close_time
        previous = get_state(db, f"research/{symbol}/{interval}/{mode}", {})
        if previous.get("as_of") == str(as_of) and previous.get("complete"):
            return
        for period in ("15m", "1h", "4h"):
            try:
                frame = self.frame_from_cache(db, symbol, period)
                if frame is None:
                    frame = self.fetch_frame(symbol, period)
                    db.execute("INSERT OR REPLACE INTO scan_cache VALUES (?,?,?,?)", (symbol, period, mode,
                        frame.to_json(orient="records", date_format="iso")))
                markets[period] = self.market(symbol, period, frame, marks)
            except Exception as exc:
                errors.append(f"{period}：{type(exc).__name__}")
                if isinstance(exc, RatePause):
                    break
        evidence = compare_periods(markets, as_of, mode)
        evidence.update(symbol=symbol, interval=interval, errors=errors, observed_at=utcnow(), attempted_at=time.time())
        set_state(db, f"research/{symbol}/{interval}/{mode}", evidence)
        # Re-read payload while holding a transaction so concurrent AI citations
        # are preserved; this adds evidence without changing signal identity/side.
        db.execute("BEGIN IMMEDIATE")
        for event in db.execute("SELECT id,payload FROM events WHERE symbol=? AND interval=? AND mode=? AND expires_at>?",
                                (symbol, interval, mode, time.time())).fetchall():
            payload = json.loads(event["payload"])
            if payload.get("kind") != "ai_note" and pd.Timestamp(payload["candle_time"]) == as_of:
                payload["multi_timeframe"] = evidence
                db.execute("UPDATE events SET payload=? WHERE id=?", (json.dumps(payload, ensure_ascii=False), event["id"]))
        db.commit()

    def relevant_news(self, symbol):
        db = research_db(self.root)
        try:
            cutoff = datetime.fromtimestamp(time.time() - 86400, timezone.utc).isoformat()
            rows = db.execute("SELECT title,url,source,published FROM news WHERE first_observed_at>=? ORDER BY first_observed_at DESC LIMIT 50", (cutoff,)).fetchall()
            base = symbol[:-4].removeprefix("1000").lower()
            keywords = [base] if len(base) >= 3 else []
            if base == "btc": keywords += ["bitcoin"]
            if base == "eth": keywords += ["ethereum"]
            return [{"title": r[0], "url": r[1], "source": r[2], "published": r[3]} for r in rows
                    if any(word in r[0].lower() for word in keywords)][:2]
        finally:
            db.close()

    def train_one(self, db, market, record):
        symbol, interval = market["symbol"], market["interval"]
        if self.demo:
            history = demo_market(symbol, interval, 1500)["candles"]
        else:
            history = validate_candles(self.client.json("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": 1500}, weight=10))
        # Leave six recent candles out of ALL fitting/selection. Current observations
        # may then be genuinely later than this version's entire training window.
        cutoff = market["candles"].iloc[-1].close_time - pd.Timedelta(seconds=6 * INTERVALS[interval])
        history = history[history.close_time < cutoff].copy()
        data_db = research_db(self.root)
        try:
            store_candles(data_db, history, symbol, interval, market["mode"])
            history = accumulated_history(data_db, symbol, interval, market["mode"])
            history = history[history.close_time < cutoff].copy()
            fitted = train_and_evaluate(history, symbol, interval, self.demo,
                horizon=record["horizon"] if record else 6,
                fee_pct=record.get("fee_pct", .05) if record else .05,
                slippage_pct=record.get("slippage_pct", .02) if record else .02)
            fitted["input_source"] = "demo" if self.demo else "binance"
            dataset = self.root / "datasets" / f'{fitted["id"]}.csv'
            dataset.parent.mkdir(parents=True, exist_ok=True)
            history.to_csv(dataset, index=False)
            save_record(self.root / "models" / "archive" / f'{fitted["id"]}.json', fitted)
            selected, audit = select_model(record, fitted, history)
            audit.update(symbol=symbol, interval=interval, mode=market["mode"], observed_at=utcnow(),
                         incumbent_id=record["id"] if record else None, candidate_id=fitted["id"])
            fitted["promotion"] = audit
            save_record(self.root / "models" / "archive" / f'{fitted["id"]}.json', fitted)
            save_record(model_path(self.root / "models", symbol, interval, self.demo), selected)
            set_state(db, f"evolution/{symbol}/{interval}/{market['mode']}", audit)
            data_db.execute("INSERT OR IGNORE INTO training_runs VALUES (?,?,?,?,?,?,?)",
                (fitted["id"], utcnow(), symbol, interval, market["mode"], int(fitted["research_pass"]), json.dumps(fitted, ensure_ascii=False)))
            data_db.commit()
            return fitted
        finally:
            data_db.close()

    def cycle(self):
        db = connect(self.root)
        started = time.time()
        settings = load_settings(self.root)
        interval, mode = settings["interval"], "demo" if self.demo else "live"
        previous = get_state(db, "status", {})
        status = {"status": "掃描中", "mode": mode, "interval": interval, "started_at": started,
                  "updated_at": started, "universe": 0, "analyzed": 0, "failed": 0, "deferred": 0,
                  "trained": 0, "models_ready": 0, "qualified": 0, "errors": []}
        try:
            if not settings["enabled"]:
                status["status"] = "已暫停"
                return status
            set_state(db, "status", status)
            symbols = self.universe(db)
            status["universe"] = len(symbols)
            marks, tickers = self.batch_context(db)
            pending, markets = [], {}
            attempts = get_state(db, "training_attempts", {})
            def process(symbol, frame):
                market = self.market(symbol, interval, frame, marks)
                row, result, record = self.evaluate(db, market, tickers.get(symbol, {}), settings)
                status["analyzed"] += 1
                status["models_ready"] += int(row["model_pass"])
                status["qualified"] += int(row["side"] != "WAIT")
                age = (pd.Timestamp.now(tz="UTC") - pd.Timestamp(record["trained_at"])).total_seconds() if record else float("inf")
                new_bars = (market["candles"].iloc[-1].close_time - pd.Timestamp(record["last_candle"])).total_seconds() / INTERVALS[interval] if record else float("inf")
                if age >= 86400 and new_bars >= 24 and result["valid"] and time.time() - attempts.get(f"{symbol}/{interval}/{mode}", 0) >= 86400:
                    markets[symbol] = (market, result, record)
                if status["analyzed"] % 20 == 0:
                    db.commit()
                    status["updated_at"] = time.time()
                    set_state(db, "status", status)
                    status["updated_at"] = time.time()
                    set_state(db, "status", status)
            for symbol in symbols:
                try:
                    frame = self.frame_from_cache(db, symbol, interval)
                    if frame is not None:
                        process(symbol, frame)
                    else:
                        pending.append(symbol)
                except Exception:
                    pending.append(symbol)
            # Bounded concurrent requests; no unbounded fanout over hundreds of symbols.
            with ThreadPoolExecutor(max_workers=4) as pool:
                for offset in range(0, len(pending), 4):
                    group = pending[offset:offset + 4]
                    jobs = {symbol: pool.submit(self.fetch_frame, symbol, interval) for symbol in group}
                    paused = False
                    for symbol, job in jobs.items():
                        try:
                            frame = job.result()
                            db.execute("INSERT OR REPLACE INTO scan_cache VALUES (?,?,?,?)", (symbol, interval, mode,
                                frame.to_json(orient="records", date_format="iso")))
                            process(symbol, frame)
                        except RatePause:
                            paused = True
                            status["deferred"] += 1
                        except Exception as exc:
                            status["failed"] += 1
                            save_result(db, {"symbol": symbol, "interval": interval, "mode": mode, "updated_at": utcnow(),
                                "side": "WAIT", "score": 0, "status": "資料不可用", "reasons": [type(exc).__name__],
                                "model_id": None, "model_pass": False, "rule_side": "WAIT", "model_side": None,
                                "price": None, "volume_24h": None, "model_probability": None})
                    db.commit()
                    if paused:
                        status["deferred"] += len(pending) - offset - len(group)
                        break
            # Directional setups first; remaining missing models are prepared too.
            eligible = [(symbol, value) for symbol, value in markets.items() if self.demo or
                (numeric(tickers.get(symbol, {}).get("quoteVolume")) is not None and
                 float(tickers[symbol]["quoteVolume"]) >= settings["min_volume_usdt"])]
            queue = sorted(eligible, key=lambda item: (-abs(item[1][1]["score"]), item[0]))
            for symbol, (market, result, record) in queue[:settings["training_per_cycle"]]:
                if numeric(tickers.get(symbol, {}).get("quoteVolume")) is None and not self.demo:
                    continue
                if not self.demo and float(tickers[symbol]["quoteVolume"]) < settings["min_volume_usdt"]:
                    continue
                try:
                    self.train_one(db, market, record)
                    status["trained"] += 1
                    attempts[f"{symbol}/{interval}/{mode}"] = time.time()
                    self.evaluate(db, market, tickers.get(symbol, {}), settings)
                except RatePause:
                    break
                except Exception as exc:
                    attempts[f"{symbol}/{interval}/{mode}"] = time.time()
                    status["errors"].append(f"{symbol} 訓練尚未完成：{type(exc).__name__}")
            set_state(db, "training_attempts", attempts)
            db.commit()
            counts = db.execute("SELECT SUM(side!='WAIT'),SUM(json_extract(payload,'$.model_pass')=1) FROM scan_results WHERE interval=? AND mode=?", (interval, mode)).fetchone()
            status["qualified"], status["models_ready"] = int(counts[0] or 0), int(counts[1] or 0)
            self.collect_qualified_shadow(db, interval, mode, marks, status)
            status["status"] = "部分完成" if status["failed"] or status["deferred"] else "完成"
            status["last_success"] = time.time()
        except Exception as exc:
            status["status"] = "連線失敗"
            status["errors"].append(str(exc) if isinstance(exc, (BinanceAccessError, RatePause)) else type(exc).__name__)
            status["last_success"] = previous.get("last_success")
        finally:
            status["updated_at"], status["duration_seconds"] = time.time(), round(time.time() - started, 2)
            set_state(db, "status", status)
            db.close()
        return status


def notification_loop(root, stopped):
    while not stopped.is_set():
        db = connect(root)
        try:
            outcome = dispatch(db, root)
            set_state(db, "delivery_status", {**outcome, "updated_at": time.time()})
        except Exception as exc:
            set_state(db, "delivery_status", {"error": type(exc).__name__, "updated_at": time.time()})
        finally:
            db.close()
        stopped.wait(2)


def ai_loop(root, stopped):
    from automatic_ai import generate_pending
    while not stopped.is_set():
        db = connect(root)
        try:
            outcome = generate_pending(db, root)
            if outcome == "no_pending_signal":
                from strategy_ai import generate as generate_strategy
                strategy_outcome = generate_strategy(db, root)
                if strategy_outcome not in ("disabled", "no_strategy_pending"):
                    outcome = "strategy_" + strategy_outcome
            set_state(db, "auto_ai_status", {"status": outcome, "updated_at": time.time()})
        except Exception as exc:
            set_state(db, "auto_ai_status", {"error": type(exc).__name__, "updated_at": time.time()})
        finally:
            db.close()
        stopped.wait(5)


def main():
    parser = argparse.ArgumentParser(description="Binance 全 USDT 永續合約研究掃描器")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    stopped = threading.Event()
    def stop(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    service = MarketScanner(demo=args.demo)
    # Complete schema initialization before the concurrent consumers start.
    connect().close()
    research_db().close()
    deliveries = commentary = strategy_worker = None
    if not args.demo:
        deliveries = threading.Thread(target=notification_loop, args=(STATE_ROOT, stopped), daemon=True)
        deliveries.start()
        commentary = threading.Thread(target=ai_loop, args=(STATE_ROOT, stopped), daemon=True)
        commentary.start()
        from strategy_worker import loop as strategy_loop
        strategy_worker = threading.Thread(target=strategy_loop, args=(STATE_ROOT, service.client, stopped), daemon=True)
        strategy_worker.start()
    try:
        while True:
            begin = time.time()
            outcome = service.cycle()
            print(json.dumps(outcome, ensure_ascii=False), flush=True)
            if not args.demo:
                data_db = research_db()
                try:
                    external_cycle(data_db, utcnow())
                except Exception:
                    pass
                finally:
                    data_db.close()
            if args.once:
                if outcome.get("status") == "連線失敗":
                    raise SystemExit(1)
                break
            stopped.wait(max(2, load_settings()["poll_seconds"] - (time.time() - begin)))
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        if deliveries:
            deliveries.join(timeout=2)
        if commentary:
            commentary.join(timeout=2)
        if strategy_worker:
            strategy_worker.join(timeout=2)


if __name__ == "__main__":
    main()

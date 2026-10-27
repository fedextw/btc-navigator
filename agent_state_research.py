"""Read-only BTC Navigator history -> offline research cycle. No background daemon."""
import argparse
import csv
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from agent_research_cycle import run_cycle, save_cycle

INTERVAL_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400}


def history_from_database(db_path, symbol, interval, mode):
    from datetime import datetime
    from agent_symbol_validation import valid_symbol
    if not valid_symbol(symbol) or interval not in INTERVAL_SECONDS or mode not in ("live", "demo"):
        raise ValueError("研究參數不正確")
    db_path = Path(db_path).resolve(strict=True)
    uri = db_path.as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
        # Explicit column selection and bound parameters; never writes to the live database.
        rows = db.execute(
            "SELECT time,open,high,low,close,volume FROM candles "
            "WHERE symbol=? AND interval=? AND mode=? ORDER BY time DESC LIMIT 10000",
            (symbol, interval, mode)).fetchall()
    rows.reverse()
    if len(rows) < 300:
        raise ValueError("累積 K 線不足 300 根，停止研究")
    # Require a continuous and timestamp-aware series: do not bridge missing bars.
    previous = None
    for item in rows:
        dt = datetime.fromisoformat(str(item[0]).replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
            raise ValueError("資料庫時間不是 UTC")
        if previous is not None and (dt-previous).total_seconds() != INTERVAL_SECONDS[interval]:
            raise ValueError("歷史 K 線有缺口或重複，停止研究")
        previous = dt
    return rows


def run_from_state(root, symbol, interval, mode, output_dir=None):
    root = Path(root).resolve()
    source = root / "research.sqlite3"
    rows = history_from_database(source, symbol, interval, mode)
    # Feed an immutable temporary CSV snapshot to existing research implementation.
    with tempfile.TemporaryDirectory(prefix="btc-agent-") as directory:
        snapshot = Path(directory) / "candles.csv"
        with snapshot.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("time", "open", "high", "low", "close", "volume"))
            writer.writerows(rows)
        report = run_cycle(snapshot)
    report["source"] = {"system": "btc-navigator-research-sqlite",
                        "symbol": symbol, "interval": interval, "mode": mode,
                        "bars": len(rows), "read_only": True}
    location = Path(output_dir) if output_dir else root / "agent-cycles"
    path = save_cycle(report, location)
    return {"report_path": str(path), "selected": report["selected"],
            "status": report["paper_status"], "reason": report["reason"],
            "bars": len(rows), "live_trading_authorized": False,
            "profitability_evidence": report["profitability_evidence"],
            "heldout_metrics": {k: report["heldout"].get(k) for k in
                ("trades","net_expectancy_r","profit_factor","max_drawdown_pct")}
                if report["heldout"] else None}


def main():
    parser = argparse.ArgumentParser(description="從 BTC Navigator 本機資料庫唯讀研究")
    parser.add_argument("--state-dir", default=".local-state")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", choices=INTERVAL_SECONDS, default="1h")
    parser.add_argument("--mode", choices=["live", "demo"], default="live")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    print(json.dumps(run_from_state(args.state_dir, args.symbol, args.interval,
                                   args.mode, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

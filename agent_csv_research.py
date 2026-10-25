"""Reproducible, offline CSV research runner. No exchange connections or order execution."""
import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

STRATEGIES = ("ema_trend", "breakout")
HORIZON = 3
COST = 0.0014  # round trip, fee+slippage assumption; research-only


def read_candles(path):
    raw = Path(path).read_bytes()
    if len(raw) > 20_000_000:
        raise ValueError("CSV 過大")
    rows = []
    data = csv.DictReader(raw.decode("utf-8-sig").splitlines())
    if not {"time", "open", "high", "low", "close", "volume"} <= set(data.fieldnames or []):
        raise ValueError("缺少 K 線必要欄位")
    previous = None
    for item in data:
        at = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
        if at.tzinfo is None or at.utcoffset().total_seconds() != 0:
            raise ValueError("時間必須使用 UTC")
        values = [float(item[key]) for key in ("open", "high", "low", "close", "volume")]
        o, h, l, c, v = values
        if not all(math.isfinite(x) for x in values) or min(o, h, l, c) <= 0 or v < 0 or l > min(o, c) or h < max(o, c):
            raise ValueError("K 線 OHLCV 不合法")
        if previous is not None and at <= previous:
            raise ValueError("時間必須遞增、不可重複")
        previous = at
        rows.append((at, o, h, l, c, v))
    if len(rows) < 300:
        raise ValueError("至少需要 300 根 K 線")
    return rows, hashlib.sha256(raw).hexdigest()


def signals(candles, strategy):
    closes = [r[4] for r in candles]
    output = [0] * len(candles)
    for i in range(50, len(candles)):
        if strategy == "ema_trend":
            fast = sum(closes[i-10:i]) / 10
            slow = sum(closes[i-50:i]) / 50
            output[i] = 1 if fast > slow and closes[i] > fast else -1 if fast < slow and closes[i] < fast else 0
        elif strategy == "breakout":
            prior = closes[i-20:i]
            output[i] = 1 if closes[i] > max(prior) else -1 if closes[i] < min(prior) else 0
        else:
            raise ValueError("未知策略")
    return output


def evaluate(candles, sides, start, stop, cost=COST):
    trades = []
    i = start
    while i + HORIZON < stop:
        side = sides[i]
        if not side:
            i += 1
            continue
        entry = candles[i+1][1]
        exit_price = candles[i+HORIZON][4]
        net = side * (exit_price / entry - 1) - cost
        trades.append({"signal_time": candles[i][0].isoformat(),
                       "exit_time": candles[i+HORIZON][0].isoformat(),
                       "side": "LONG" if side == 1 else "SHORT",
                       "net_return": net})
        i += HORIZON
    returns = [t["net_return"] for t in trades]
    equity = high = 1.0
    drawdown = 0.0
    for value in returns:
        equity *= (1 + value)
        high = max(high, equity)
        drawdown = max(drawdown, 1 - equity/high) if high else 1.0
    profit = sum(max(0, r) for r in returns)
    loss = -sum(min(0, r) for r in returns)
    return {"trades": len(trades), "trading_days": len({t["exit_time"][:10] for t in trades}),
            "net_expectancy_r": sum(returns)/len(returns) if returns else 0.0,
            "max_drawdown_pct": drawdown*100,
            "profit_factor": profit/loss if loss else 0.0,
            "net_return_pct": (equity-1)*100,
            "trades_detail": trades}


def research(path, strategy="all", cost=COST):
    if not 0 <= cost <= 0.1:
        raise ValueError("成本率必須介於0和0.1")
    candles, digest = read_candles(path)
    n = len(candles)
    train_end = int(n*0.6)
    validation_end = int(n*0.8)
    strategy_names = STRATEGIES if strategy == "all" else (strategy,)
    if any(s not in STRATEGIES for s in strategy_names):
        raise ValueError("策略名稱錯誤")
    candidates = []
    for name in strategy_names:
        side = signals(candles, name)
        validation = evaluate(candles, side, train_end, validation_end, cost)
        candidates.append((name, validation))
    # Select ONLY using validation performance; held-out segment is untouched until selection.
    winner = max(candidates, key=lambda x: (x[1]["net_expectancy_r"], -x[1]["max_drawdown_pct"], x[0]))
    selected, validation = winner
    heldout = evaluate(candles, signals(candles, selected), validation_end, n, cost)
    # The first trade requires signal and entry after validation boundary. No overlap across splits.
    proposal = {
        "hypothesis": "Predefined offline strategy: " + selected,
        "dataset_fingerprint": digest, "code_commit": "local-csv-experiment-v1",
        "train_end_utc": candles[train_end-1][0].isoformat(),
        "test_start_utc": candles[validation_end][0].isoformat(),
        "test_end_utc": candles[-1][0].isoformat(),
        "trades": heldout["trades"], "trading_days": heldout["trading_days"],
        "net_expectancy_r": heldout["net_expectancy_r"],
        "max_drawdown_pct": heldout["max_drawdown_pct"],
        "profit_factor": heldout["profit_factor"],
        "costs_included": True, "lookahead_checked": True,
        "heldout_untouched": True, "paper_only": True,
    }
    from agent_research_gate import assess
    assessment = assess(proposal)
    assessment["status"] = "requires_independent_replication" if assessment["status"] == "eligible_for_independent_review" else "rejected"
    assessment["note"] = "本次已由 CSV 計算績效，但原始資料真實性、價格可成交性及策略樣本外獨立性尚未驗證。"
    return {"dataset_sha256": digest, "candles": n, "selected_strategy": selected,
            "validation": {k:v for k,v in validation.items() if k != "trades_detail"},
            "heldout": {k:v for k,v in heldout.items() if k != "trades_detail"},
            "proposal": proposal, "assessment": assessment,
            "note": "離線紙上研究；不接交易所，不做實盤，不自動晉升策略。策略只用驗證段挑選，測試段僅一次檢驗。"}


def main():
    parser = argparse.ArgumentParser(description="離線 CSV 自動策略比較與保留測試")
    parser.add_argument("csv_file")
    parser.add_argument("--strategy", choices=["all", *STRATEGIES], default="all")
    parser.add_argument("--cost", type=float, default=COST)
    parser.add_argument("--output", default="research_result.json")
    args = parser.parse_args()
    result = research(args.csv_file, args.strategy, args.cost)
    out = Path(args.output)
    with out.open("x", encoding="utf-8") as target:
        json.dump(result, target, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({"result_file": str(out), "strategy": result["selected_strategy"],
                      "heldout": result["heldout"], "gate": result["assessment"]["status"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

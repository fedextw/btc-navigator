"""Deterministic parameter research cycle: offline, paper-only, never promotes models."""
import argparse
import hashlib
import json
from pathlib import Path

from agent_csv_research import read_candles, evaluate, COST
from agent_profitability_gate import assess

# Small, predeclared search budget. No learned strategy code execution.
CANDIDATES = (
    ("trend_8_30", "trend", 8, 30),
    ("trend_10_50", "trend", 10, 50),
    ("trend_20_80", "trend", 20, 80),
    ("breakout_15", "breakout", 15, 0),
    ("breakout_20", "breakout", 20, 0),
    ("breakout_40", "breakout", 40, 0),
)


def make_signals(bars, candidate):
    _, family, fast, slow = candidate
    close = [r[4] for r in bars]
    sides = [0] * len(close)
    warmup = max(80, slow, fast)
    for i in range(warmup, len(close)):
        if family == "trend":
            a = sum(close[i-fast:i]) / fast
            b = sum(close[i-slow:i]) / slow
            sides[i] = 1 if a > b and close[i] > a else -1 if a < b and close[i] < a else 0
        else:
            past = close[i-fast:i]
            sides[i] = 1 if close[i] > max(past) else -1 if close[i] < min(past) else 0
    return sides


def run_cycle(csv_path, *, cost=COST):
    if not 0 <= cost <= 0.1:
        raise ValueError("不合法的成本率")
    bars, fingerprint = read_candles(csv_path)
    n = len(bars)
    # Each segment evaluated independently with a 3-bar safety buffer.
    val_start, test_start = int(n*.6), int(n*.8)
    comparisons = []
    for candidate in CANDIDATES:
        outcomes = evaluate(bars, make_signals(bars, candidate), val_start, test_start, cost)
        comparisons.append({"candidate": candidate[0],
                            "validation": {k:v for k,v in outcomes.items() if k != "trades_detail"}})
    # Minimum 5 validation trades; otherwise no selection and no holdout peek.
    valid = [c for c in comparisons if c["validation"]["trades"] >= 5]
    chosen = None
    heldout = None
    reason = "驗證段沒有至少5筆的候選" if not valid else None
    evidence = assess(None)
    if valid:
        selected = max(valid, key=lambda c: (
            c["validation"]["net_expectancy_r"],
            -c["validation"]["max_drawdown_pct"], c["candidate"]))
        chosen = selected["candidate"]
        candidate = next(c for c in CANDIDATES if c[0] == chosen)
        result = evaluate(bars, make_signals(bars, candidate), test_start, n, cost)
        heldout = {k:v for k,v in result.items() if k != "trades_detail"}
        evidence = assess(result)
        reason = ("初步保留測試通過；仍需獨立前向模擬複驗" if evidence["eligible"]
                  else "；".join(evidence["reasons"]))
    return {
        "schema": "agent-cycle-v1", "dataset_sha256": fingerprint,
        "config": {"bars": n, "cost_fraction": cost, "horizon_bars": 3,
                   "train_end": bars[val_start-1][0].isoformat(),
                   "validation_end": bars[test_start-1][0].isoformat(),
                   "heldout_end": bars[-1][0].isoformat()},
        "candidates": comparisons, "selected": chosen, "heldout": heldout,
        "profitability_evidence": evidence,
        "paper_status": "research_candidate" if chosen and reason.startswith("初步") else "rejected",
        "reason": reason,
        "live_trading_authorized": False,
        "note": "固定六組參數自動比較，不是生成式AI自主寫策略；資料真偽、實際成交和重複研究偏差未獨立確認。",
    }


def save_cycle(report, directory):
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    target = out / (digest + ".json")
    try:
        with target.open("x", encoding="utf-8") as f:
            f.write(payload)
    except FileExistsError:
        if target.read_text(encoding="utf-8") != payload:
            raise RuntimeError("研究內容指紋衝突")
    return target


def main():
    parser = argparse.ArgumentParser(description="B+C 離線參數研究循環")
    parser.add_argument("csv_file", help="UTC OHLCV CSV")
    parser.add_argument("--output-dir", default=".local-state/agent-cycles")
    parser.add_argument("--cost", type=float, default=COST)
    args = parser.parse_args()
    report = run_cycle(args.csv_file, cost=args.cost)
    path = save_cycle(report, args.output_dir)
    print(json.dumps({"saved_to": str(path), "selected": report["selected"],
                      "paper_status": report["paper_status"], "reason": report["reason"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

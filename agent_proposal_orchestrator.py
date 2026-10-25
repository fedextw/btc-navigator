"""Bounded, deterministic proposal orchestrator: no model/API keys, no order access.

Produces proposal specifications from a fixed grammar, validates each on the
chronological validation window, and saves a content-addressed report. A future
LLM can suggest specs through the same constrained interface, not run code.
"""
import argparse
import hashlib
import json
from pathlib import Path

from agent_csv_research import read_candles, evaluate, COST
from agent_research_cycle import make_signals
from agent_strategy_proposals import validate

MAX_PROPOSALS = 12


def propose():
    """Pre-registered ideas; no claim that an LLM invented them."""
    specs = []
    for fast, slow in ((8, 30), (10, 50), (15, 60), (20, 80)):
        specs.append({"family": "trend", "lookback": fast, "slow": slow,
                      "rationale": "預先登記：短長均線方向與收盤確認"})
    for lookback in (12, 20, 30, 40):
        specs.append({"family": "breakout", "lookback": lookback, "slow": 0,
                      "rationale": "預先登記：突破過去收盤區間"})
    return specs


def experiment(csv_path, cost=COST):
    if not 0 <= cost <= .1:
        raise ValueError("交易成本參數無效")
    bars, fingerprint = read_candles(csv_path)
    start, end = int(len(bars)*.6), int(len(bars)*.8)
    specs = propose()
    if len(specs) > MAX_PROPOSALS:
        raise ValueError("候選數超出預先規定上限")
    results = []
    for spec in specs:
        candidate = validate(spec)
        stats = evaluate(bars, make_signals(bars, candidate), start, end, cost)
        result = {k: v for k,v in stats.items() if k != "trades_detail"}
        valid = (stats["trades"] >= 5 and stats["net_expectancy_r"] > 0
                 and stats["max_drawdown_pct"] < 15
                 and stats["profit_factor"] >= 1.1)
        results.append({"spec": spec, "strategy": candidate[0],
                        "validation": result, "status": "validation_pass" if valid else "rejected"})
    winners = [r for r in results if r["status"] == "validation_pass"]
    selected = max(winners, key=lambda r: (
        r["validation"]["net_expectancy_r"],
        -r["validation"]["max_drawdown_pct"], r["strategy"])) if winners else None
    return {
        "schema": "agent-orchestrator-v1", "source": "pre_registered_parameter_grammar",
        "dataset_sha256": fingerprint, "cost_fraction": cost,
        "candidate_count": len(results), "candidates": results,
        "selected": selected["strategy"] if selected else None,
        "status": "awaiting_new_holdout_and_forward_test" if selected else "no_qualified_candidate",
        "paper_only": True, "live_trading_authorized": False,
        "note": "此工具不使用 LLM、不自行產生任意程式碼、未讀取保留測試區間，也不更改任何既有策略或交易訊號。",
    }


def save_report(result, output_dir):
    data = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    identity = hashlib.sha256(data.encode()).hexdigest()
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (identity + ".json")
    try:
        with path.open("x", encoding="utf-8") as f:
            f.write(data)
    except FileExistsError:
        if path.read_text(encoding="utf-8") != data:
            raise RuntimeError("研究報告指紋不一致")
    return path


def main():
    p = argparse.ArgumentParser(description="Agent 受控提案與驗證循環")
    p.add_argument("csv")
    p.add_argument("--out", default=".local-state/agent-proposals")
    args = p.parse_args()
    report = experiment(args.csv)
    path = save_report(report, args.out)
    print(json.dumps({"saved": str(path), "selected": report["selected"],
                      "status": report["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

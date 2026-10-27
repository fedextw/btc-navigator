"""Bounded, deterministic proposal orchestrator: no model/API keys, no order access.

Produces proposal specifications from a fixed grammar, validates each on the
chronological validation window, and saves a content-addressed report. A future
LLM can suggest specs through the same constrained interface, not run code.
"""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from agent_csv_research import read_candles, evaluate, COST
from agent_research_cycle import make_signals
from agent_strategy_proposals import validate
from agent_evolution import evolve

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


def experiment(csv_path, cost=COST, ancestor=None, ai_proposals=None):
    if not 0 <= cost <= .1:
        raise ValueError("交易成本參數無效")
    bars, fingerprint = read_candles(csv_path)
    start, end = int(len(bars)*.6), int(len(bars)*.8)
    if ai_proposals is not None:
        if ancestor is not None:
            raise ValueError("AI 提案與既有跨代進化不可在同一輪混用")
        if not isinstance(ai_proposals, list) or not 1 <= len(ai_proposals) <= MAX_PROPOSALS:
            raise ValueError("AI 提案數量須為 1 至 12")
        specs = ai_proposals
        for spec in specs:
            validate(spec)
        lineage = None
        source = "external_ai_specifications"
    elif ancestor is None:
        specs = propose()
        lineage = None
        source = "pre_registered_parameter_grammar"
    else:
        if not isinstance(ancestor, dict) or ancestor.get("schema") != "agent-orchestrator-v1":
            raise ValueError("不合法的上一代研究報告")
        if ancestor.get("paper_only") is not True or ancestor.get("live_trading_authorized") is not False:
            raise ValueError("上一代研究權限不安全")
        if type(ancestor.get("cost_fraction")) not in (int, float) or ancestor["cost_fraction"] != cost:
            raise ValueError("跨代研究成本假設不一致")
        if not isinstance(ancestor.get("candidates"), list) or ancestor.get("candidate_count") != len(ancestor["candidates"]):
            raise ValueError("上一代研究證據數量不一致")
        if ancestor.get("dataset_sha256") == fingerprint:
            raise ValueError("下一代研究不可重用上一代相同的資料集")
        prior_latest = ancestor.get("dataset_latest_utc")
        if not isinstance(prior_latest, str):
            raise ValueError("上一代缺少資料截止時間，無法證明跨代獨立")
        try:
            cutoff = datetime.fromisoformat(prior_latest)
        except ValueError as exc:
            raise ValueError("上一代截止時間格式錯誤") from exc
        if cutoff.tzinfo is None or cutoff.utcoffset().total_seconds() != 0:
            raise ValueError("上一代截止時間必須為 UTC")
        if bars[start][0] <= cutoff:
            raise ValueError("下一代驗證期間與上一代資料重疊")
        lineage = evolve(ancestor)
        specs = lineage["proposals"]
        source = "validation_guided_evolution"
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
        "schema": "agent-orchestrator-v1", "source": source,
        "parent_report_sha256": lineage["parent_report_sha256"] if lineage else None,
        "external_proposals_sha256": hashlib.sha256(json.dumps(specs,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest() if ai_proposals is not None else None,
        "dataset_sha256": fingerprint, "cost_fraction": cost,
        "dataset_latest_utc": bars[-1][0].isoformat(),
        "validation_start_utc": bars[start][0].isoformat(),
        "candidate_count": len(results), "candidates": results,
        "selected": selected["strategy"] if selected else None,
        "status": "awaiting_new_holdout_and_forward_test" if selected else "no_qualified_candidate",
        "paper_only": True, "live_trading_authorized": False,
        "note": "只研究受控策略規格；可接收外部 AI 提案但不自行呼叫 LLM、不執行策略程式碼、不碰保留區間及真實訂單。",
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
    p.add_argument("--ancestor", help="上一代研究 JSON；使用不同資料集進行下一代驗證")
    p.add_argument("--ai-proposals", help="外部 AI 所提出的策略規格 JSON 陣列；僅支援受控策略家族")
    args = p.parse_args()
    ancestor = json.loads(Path(args.ancestor).read_text(encoding="utf-8")) if args.ancestor else None
    proposals = json.loads(Path(args.ai_proposals).read_text(encoding="utf-8")) if args.ai_proposals else None
    report = experiment(args.csv, ancestor=ancestor, ai_proposals=proposals)
    path = save_report(report, args.out)
    print(json.dumps({"saved": str(path), "selected": report["selected"],
                      "status": report["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Safe agent-generated strategy specification, without eval or executable code.

An external LLM may propose JSON *parameters*; only vetted built-in strategy
families execute. A proposed specification never authorizes live trading.
"""
import hashlib
import json
from pathlib import Path
from agent_csv_research import read_candles, evaluate, COST
from agent_research_cycle import make_signals

FAMILIES = {"trend", "breakout"}
MAX_SPEC_SIZE = 16_384


def validate(spec):
    if not isinstance(spec, dict) or set(spec) != {"family", "lookback", "slow", "rationale"}:
        raise ValueError("研究提案欄位不正確")
    family, fast, slow = spec["family"], spec["lookback"], spec["slow"]
    if family not in FAMILIES or type(fast) is not int or type(slow) is not int:
        raise ValueError("策略家族或週期格式錯誤")
    if not 5 <= fast <= 60 or not (fast+5 <= slow <= 160 if family == "trend" else slow == 0):
        raise ValueError("參數超出安全研究範圍")
    if not isinstance(spec["rationale"], str) or not 1 <= len(spec["rationale"]) <= 500:
        raise ValueError("缺少研究假設")
    return (f"agent_{family}_{fast}_{slow}", family, fast, slow)


def study(csv_path, spec_file, cost=COST):
    source = Path(spec_file).read_bytes()
    if len(source) > MAX_SPEC_SIZE:
        raise ValueError("提案檔過大")
    spec = json.loads(source)
    candidate = validate(spec)
    if not 0 <= cost <= 0.1:
        raise ValueError("成本設定異常")
    candles, dataset_hash = read_candles(csv_path)
    n = len(candles)
    # Deliberately evaluate validation only. Heldout data is never touched
    # during agent candidate screening, preventing selection on future outcomes.
    start, end = int(n*.6), int(n*.8)
    stats = evaluate(candles, make_signals(candles, candidate), start, end, cost)
    accepted = (stats["trades"] >= 5 and stats["net_expectancy_r"] > 0
                and stats["max_drawdown_pct"] < 15 and stats["profit_factor"] >= 1.1)
    return {
        "schema": "agent-proposal-study-v1",
        "strategy": candidate[0],
        "proposal_sha256": hashlib.sha256(source).hexdigest(),
        "dataset_sha256": dataset_hash,
        "validation": {k:v for k,v in stats.items() if k != "trades_detail"},
        "status": "candidate_for_future_holdout" if accepted else "rejected",
        "paper_only": True, "live_trading_authorized": False,
        "note": "僅評估驗證區間。候選尚需保留測試、前向紙上驗證及獨立審查；不得晉升實盤。",
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="外部 AI JSON 研究提案安全驗證")
    parser.add_argument("candles_csv")
    parser.add_argument("proposal_json")
    args = parser.parse_args()
    print(json.dumps(study(args.candles_csv, args.proposal_json), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

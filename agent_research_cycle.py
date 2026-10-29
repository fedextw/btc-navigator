"""Deterministic parameter research cycle: offline, paper-only, never promotes models."""
import argparse
import hashlib
import json
from pathlib import Path

from agent_csv_research import read_candles, evaluate, COST
from agent_profitability_gate import assess

# Bounded, deterministic strategy-parameter exploration; never execute generated code.
# Candidate selection uses validation only; held-out samples remain untouched.
TREND_PAIRS = ((5,20),(8,30),(10,50),(12,48),(15,60),(20,80),(30,100),(40,160))
BREAKOUT_WINDOWS = (10,15,20,30,40,60,80,120)
CANDIDATES = tuple(
    (f"trend_{fast}_{slow}", "trend", fast, slow)
    for fast,slow in TREND_PAIRS
) + tuple(
    (f"breakout_{window}", "breakout", window, 0)
    for window in BREAKOUT_WINDOWS
)
assert len(CANDIDATES) == 16



def generate_followup_candidates(comparisons):
    """Bounded proposals around validation leaders; no access to held-out trades."""
    if not isinstance(comparisons,list):
        raise ValueError("研究結果格式不正確")
    seeds=sorted(
        (r for r in comparisons if isinstance(r,dict)
         and isinstance(r.get("validation"),dict)
         and r["validation"].get("trades",0)>=5),
        key=lambda r:(-r["validation"]["net_expectancy_r"],
                      r["validation"]["max_drawdown_pct"],r["candidate"])
    )[:2]
    existing={c[0] for c in CANDIDATES}
    proposals=[]
    for seed in seeds:
        named=seed["candidate"]
        parent=next((c for c in CANDIDATES if c[0]==named),None)
        if parent is None:
            continue
        _,family,fast,slow=parent
        if family=="trend":
            variants=((max(3,fast-2),slow),(fast+2,slow),
                      (fast,max(fast+5,slow-5)),(fast,slow+5))
        else:
            variants=((max(5,fast-3),0),(fast+3,0))
        for f,s in variants:
            if f>=s and family=="trend":
                continue
            label=f"{family}_{f}_{s}" if family=="trend" else f"breakout_{f}"
            if label not in existing and all(c[0]!=label for c in proposals):
                proposals.append((label,family,f,s))
            if len(proposals)>=8:
                return tuple(proposals)
    return tuple(proposals)


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
        elif family == "breakout":
            past = close[i-fast:i]
            sides[i] = 1 if close[i] > max(past) else -1 if close[i] < min(past) else 0
        elif family == "mean_reversion":
            # Countertrend hypothesis: price dislocation from trailing mean.
            # Threshold is a fixed basis-point multiple, not generated code.
            baseline = sum(close[i-fast:i]) / fast
            deviation = (close[i] / baseline - 1)
            threshold = slow / 10000
            sides[i] = -1 if deviation > threshold else 1 if deviation < -threshold else 0
        else:
            raise ValueError("Unknown signal family")
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
    # Second bounded search is explicitly exploratory: validation is reused
    # to propose neighbors. Holdout is still untouched until final selection.
    followups=generate_followup_candidates(comparisons)
    for candidate in followups:
        outcomes=evaluate(bars,make_signals(bars,candidate),val_start,test_start,cost)
        comparisons.append({"candidate":candidate[0],
                            "validation":{k:v for k,v in outcomes.items()
                                          if k!="trades_detail"}})
    # Evaluate validation-period stability in two chronological, disjoint
    # windows. This is still development data; neither window is a fresh
    # prospective test and the held-out partition remains untouched.
    midpoint = (val_start + test_start) // 2
    for entry in comparisons:
        candidate = next(c for c in (*CANDIDATES,*followups) if c[0] == entry["candidate"])
        sides = make_signals(bars,candidate)
        halves = [evaluate(bars,sides,val_start,midpoint,cost),
                  evaluate(bars,sides,midpoint,test_start,cost)]
        entry["validation_stability"] = {
            "half_trades": [h["trades"] for h in halves],
            "half_net_expectancy_r": [h["net_expectancy_r"] for h in halves],
            "both_halves_positive": all(h["trades"]>=3 and h["net_expectancy_r"]>0
                                         for h in halves),
        }
    # Do not promote the highest single-period result if one half has no
    # positive net evidence; stronger holdout alone cannot rescue selection.
    valid = [c for c in comparisons
             if c["validation"]["trades"] >= 6
             and c["validation_stability"]["both_halves_positive"]]
    chosen = None
    heldout = None
    reason = "驗證區間兩段未同時證明正淨期望值與足夠交易數" if not valid else None
    evidence = assess(None)
    if valid:
        selected = max(valid, key=lambda c: (
            c["validation"]["net_expectancy_r"],
            -c["validation"]["max_drawdown_pct"], c["candidate"]))
        chosen = selected["candidate"]
        candidate = next(c for c in (*CANDIDATES,*followups) if c[0] == chosen)
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
        "candidates": comparisons, "followup_candidate_count": len(followups),
        "selection_bias_warning": "validation_reused_for_adaptive_search_requires_fresh_forward_test",
        "selected": chosen, "heldout": heldout,
        "profitability_evidence": evidence,
        "paper_status": "research_candidate" if chosen and reason.startswith("初步") else "rejected",
        "reason": reason,
        "live_trading_authorized": False,
        "note": "16組基礎候選加最多8組自動參數探索；兩段驗證只是歷史穩定性篩選，非獨立前向證據。",
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

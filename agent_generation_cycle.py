"""Bounded offline multigeneration replay with immutable evidence.

Snapshots chronological candle prefixes; never grants trading permissions.
Research continues only if the next generation has a fresh validation window.
"""
import argparse
import csv
import json
import tempfile
from pathlib import Path

from agent_csv_research import read_candles
from agent_proposal_orchestrator import experiment, save_report

MAX_GENERATIONS = 3

def run_generations(csv_path, output_dir, boundaries, cost=0.0014):
    if not isinstance(boundaries, (list, tuple)) or not 1 <= len(boundaries) <= MAX_GENERATIONS:
        raise ValueError("Only 1-3 research generations supported")
    if any(type(n) is not int or n < 300 for n in boundaries):
        raise ValueError("Invalid chronological cutoff")
    if boundaries != sorted(set(boundaries)):
        raise ValueError("Cutoffs must be strictly increasing")
    candles, _ = read_candles(csv_path)
    if boundaries[-1] > len(candles):
        raise ValueError("Cutoff exceeds available candles")
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Do not overwrite an earlier research run")
    reports = []
    ancestor = None
    stop_reason = None
    with tempfile.TemporaryDirectory() as directory:
        snapshot = Path(directory) / "closed_candles.csv"
        for cutoff in boundaries:
            if ancestor is not None and ancestor.get("selected") is None:
                stop_reason = "no_qualified_parent_for_next_generation"
                break
            with snapshot.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(("time", "open", "high", "low", "close", "volume"))
                for bar in candles[:cutoff]:
                    writer.writerow((bar[0].isoformat(), *bar[1:]))
            result = experiment(snapshot, cost=cost, ancestor=ancestor)
            reports.append(result)
            ancestor = result
    output.mkdir(parents=True, exist_ok=True)
    paths = [save_report(report, output) for report in reports]
    return {"schema":"agent-generations-v1", "generations":len(paths),
            "evidence_paths":[str(p) for p in paths],
            "sources":[r["source"] for r in reports],
            "requested_generations": len(boundaries),
            "stop_reason": stop_reason,
            "paper_only":True,"live_trading_authorized":False,
            "status":"research_only_no_promotion"}

def main():
    parser = argparse.ArgumentParser(description="離線跨代策略研究；禁止實盤下單")
    parser.add_argument("csv")
    parser.add_argument("--out", required=True)
    parser.add_argument("--cutoffs", nargs="+", required=True, type=int)
    args=parser.parse_args()
    print(json.dumps(run_generations(args.csv,args.out,args.cutoffs), ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()

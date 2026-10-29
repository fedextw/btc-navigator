"""Read-only SQLite snapshot to bounded, deterministic candidate research.

No order execution, model promotion, or network calls.
"""
import csv
import tempfile
from pathlib import Path

from agent_state_research import history_from_database
from agent_proposal_orchestrator import experiment, save_report


def research_from_state(state_dir, symbol, interval="1h", mode="live"):
    root = Path(state_dir).resolve()
    rows = history_from_database(root / "research.sqlite3", symbol, interval, mode)
    with tempfile.TemporaryDirectory(prefix="btc-agent-proposals-") as temp:
        snapshot = Path(temp) / "history.csv"
        with snapshot.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("time", "open", "high", "low", "close", "volume"))
            writer.writerows(rows)
        report = experiment(snapshot)
    report["source"] = {"system": "btc-navigator-research-sqlite",
                        "symbol": symbol, "interval": interval, "mode": mode,
                        "bars": len(rows), "read_only": True}
    location = save_report(report, root / "agent-proposals")
    return {"report_path": str(location), "selected": report["selected"],
            "status": report["status"], "bars": len(rows),
            "live_trading_authorized": False}

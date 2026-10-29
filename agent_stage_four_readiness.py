"""Conservative, no-billing freshness gate before reserving a new AI research slot.

The validation split uses the most recent 40 percent of a fixed-size candle
window. To be strictly disjoint from the previous report, at least that many
new CLOSED candles must exist. This time gate is a necessary condition, not a
replacement for check_feedback_readiness on the downloaded dataset.
"""
import json
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

_INTERVAL_MINUTES = {"15m": 15, "1h": 60, "4h": 240}


def check_batch_readiness(state_dir, symbols, *, interval="1h", count=1600, now=None):
    if interval not in _INTERVAL_MINUTES or type(count) is not int or count < 100:
        raise ValueError("Unsupported candle interval or count")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise ValueError("Current time must be UTC")
    waiting = []
    for symbol in symbols:
        path = Path(state_dir) / "markets" / symbol / interval / "stage4-checkpoint.json"
        if not path.exists():
            continue  # A fresh symbol may bootstrap its first generation.
        if path.stat().st_size > 8192:
            raise ValueError("Oversized per-market checkpoint")
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        if checkpoint.get("schema") != "agent-stage4-checkpoint-v1":
            raise ValueError("Invalid per-market checkpoint")
        if checkpoint.get("status") != "completed":
            # This is NOT a normal wait: an interrupted model call needs review.
            return {"status": "requires_manual_review", "symbol": symbol,
                    "paper_only": True, "live_trading_authorized": False}
        report_path = checkpoint.get("report_path")
        if not isinstance(report_path, str) or not Path(report_path).is_file():
            raise ValueError("Missing completed research report")
        parent = Path(report_path)
        raw = parent.read_bytes()
        if parent.suffix != ".json" or parent.stem != hashlib.sha256(raw).hexdigest():
            raise ValueError("Previous report checksum does not match filename")
        report = json.loads(raw)
        if report.get("schema") != "agent-orchestrator-v1" or report.get("paper_only") is not True:
            raise ValueError("Invalid previous research provenance")
        latest = datetime.fromisoformat(report["dataset_latest_utc"])
        if latest.tzinfo is None or latest.utcoffset() != timedelta(0):
            raise ValueError("Previous dataset cutoff is not UTC")
        # One extra interval for a fully closed current candle and clock skew.
        required = latest + timedelta(minutes=_INTERVAL_MINUTES[interval] * (count - int(count * .6) + 1))
        if current <= required:
            waiting.append({"symbol": symbol, "earliest_retry_utc": required.isoformat()})
    return {"status": "waiting_for_fresh_data" if waiting else "ready",
            "waiting": waiting, "paper_only": True, "live_trading_authorized": False}

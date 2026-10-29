"""Fail-closed intake gate for external AI research agents.

This module is deliberately independent of trading execution and does not import
order routing code. Agent-produced claims never authorize live trading.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

REQUIRED = (
    "hypothesis", "dataset_fingerprint", "code_commit",
    "train_end_utc", "test_start_utc", "test_end_utc",
    "trades", "trading_days", "net_expectancy_r", "max_drawdown_pct",
    "profit_factor", "costs_included", "lookahead_checked",
    "heldout_untouched", "paper_only",
)
MAX_BYTES = 64 * 1024


def _utc(value: Any) -> str:
    from datetime import datetime, timezone
    if not isinstance(value, str):
        raise ValueError("時間必須是 UTC ISO 格式字串")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError("時間必須明確標示 UTC")
    return stamp.astimezone(timezone.utc).isoformat()


def assess(proposal: dict[str, Any]) -> dict[str, Any]:
    """Review agent-supplied evidence; return a research decision, never a trade approval."""
    if not isinstance(proposal, dict):
        raise ValueError("研究提案必須是 JSON 物件")
    missing = [field for field in REQUIRED if field not in proposal]
    if missing:
        return {"status": "rejected", "checks": {}, "reasons": ["缺少欄位：" + ", ".join(missing)],
                "live_trading_authorized": False}
    for name in ("costs_included", "lookahead_checked", "heldout_untouched", "paper_only"):
        if type(proposal[name]) is not bool:
            raise ValueError(name + " 必須為布林值")
    for name in ("trades", "trading_days"):
        if type(proposal[name]) is not int or proposal[name] < 0:
            raise ValueError(name + " 必須為非負整數")
    for name in ("net_expectancy_r", "max_drawdown_pct", "profit_factor"):
        value = proposal[name]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(name + " 必須為有限數值")
    for name in ("hypothesis", "dataset_fingerprint", "code_commit"):
        if not isinstance(proposal[name], str) or not proposal[name].strip():
            raise ValueError(name + " 不可為空")
    start, test_start, end = (_utc(proposal[key]) for key in
                               ("train_end_utc", "test_start_utc", "test_end_utc"))
    checks = {
        "訓練結束早於保留測試起點": start < test_start < end,
        "至少100筆保留測試交易": proposal["trades"] >= 100,
        "至少20個交易日": proposal["trading_days"] >= 20,
        "成本後期望淨R為正": proposal["net_expectancy_r"] > 0,
        "最大回撤低於15%": 0 <= proposal["max_drawdown_pct"] < 15,
        "Profit factor至少1.1": proposal["profit_factor"] >= 1.1,
        "已納入成本": proposal["costs_included"],
        "已檢查前視偏差": proposal["lookahead_checked"],
        "測試集未被用來挑選策略": proposal["heldout_untouched"],
        "僅允許紙上研究": proposal["paper_only"],
    }
    reasons = [key for key, passed in checks.items() if not passed]
    return {
        "status": "eligible_for_independent_review" if not reasons else "rejected",
        "checks": checks, "reasons": reasons,
        "live_trading_authorized": False,
        "note": "僅檢查提案自陳資料；不是獨立驗證，也不允許實盤下單。",
    }


def review_file(proposal_file: str | Path, audit_dir: str | Path) -> dict[str, Any]:
    """Write a content-addressed, append-only audit record; never overwrite a previous audit."""
    path = Path(proposal_file)
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("研究提案超過大小上限")
    payload = json.loads(raw)
    result = assess(payload)
    digest = hashlib.sha256(raw).hexdigest()
    result["proposal_sha256"] = digest
    record = {"proposal": payload, "assessment": result}
    destination = Path(audit_dir)
    destination.mkdir(parents=True, exist_ok=True)
    file_path = destination / (digest + ".json")
    content = json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
    # x mode guarantees no silent overwrite of historical decisions.
    try:
        with file_path.open("x", encoding="utf-8") as handle:
            handle.write(content + "\n")
    except FileExistsError:
        existing = json.loads(file_path.read_text(encoding="utf-8"))
        if existing != record:
            raise RuntimeError("相同資料指紋的稽核紀錄不一致")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI研究提案審核（不包含交易權限）")
    parser.add_argument("proposal_json")
    parser.add_argument("--audit-dir", default=".local-state/agent-audit")
    args = parser.parse_args()
    print(json.dumps(review_file(args.proposal_json, args.audit_dir),
                     ensure_ascii=False, indent=2))

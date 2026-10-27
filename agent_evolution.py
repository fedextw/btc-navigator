"""Evidence-guided candidate evolution (paper research only).

Uses *validation* evidence from previous generations. No holdout feedback,
arbitrary code, API keys, or trading privileges. This is not an LLM.
"""
import hashlib
import json
from agent_strategy_proposals import validate

MAX_PARENTS = 24
MAX_CHILDREN = 12

def diagnose(metrics):
    """Interpret validation-only evidence; diagnostics are hypotheses, not causal proof."""
    if metrics["trades"] < 5:
        return "insufficient_samples"
    if metrics["max_drawdown_pct"] >= 15:
        return "excess_drawdown"
    if metrics["net_expectancy_r"] <= 0:
        return "nonpositive_net_expectancy"
    return "requires_independent_replication"

def evolve(previous_report):
    if not isinstance(previous_report, dict) or not isinstance(previous_report.get("candidates"), list):
        raise ValueError("Invalid ancestor report")
    if len(previous_report["candidates"]) > MAX_PARENTS:
        raise ValueError("Too many parent candidates")
    if previous_report.get("source") not in ("pre_registered_parameter_grammar", "validation_guided_evolution"):
        raise ValueError("Untrusted ancestor provenance")
    ancestor_hash = hashlib.sha256(json.dumps(previous_report, sort_keys=True, ensure_ascii=False,
                                              allow_nan=False).encode("utf-8")).hexdigest()
    ranked = []
    for item in previous_report["candidates"]:
        if not isinstance(item, dict) or not isinstance(item.get("validation"), dict):
            raise ValueError("Malformed candidate")
        spec = item.get("spec")
        validate(spec)
        metrics = item["validation"]
        if any(type(metrics.get(k)) not in (int, float) for k in
               ("net_expectancy_r", "max_drawdown_pct", "trades")):
            raise ValueError("Missing validation evidence")
        if not (-10000 <= metrics["net_expectancy_r"] <= 10000
                and 0 <= metrics["max_drawdown_pct"] <= 100
                and 0 <= metrics["trades"] <= 10000):
            raise ValueError("Out-of-range evidence")
        ranked.append((metrics["net_expectancy_r"] - max(0, metrics["max_drawdown_pct"]) * .01,
                       metrics["trades"], spec))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]["family"], item[2]["lookback"]))
    diagnostics = [{"strategy": validate(item["spec"])[0],
                    "reason": diagnose(item["validation"])}
                   for item in previous_report["candidates"]]
    children, seen = [], set()
    for _, _, parent in ranked[:4]:
        parent_name = validate(parent)[0]
        failure = next(x["reason"] for x in diagnostics if x["strategy"] == parent_name)
        for delta in (-3, 3):
            fast = parent["lookback"] + delta
            slow = parent["slow"] + 2 * delta if parent["family"] == "trend" else 0
            child = {"family": parent["family"], "lookback": fast, "slow": slow,
                     "rationale": "上一代診斷：" + failure + "；局部參數變異仍須獨立驗證"}
            try:
                validate(child)
            except ValueError:
                continue
            identity = (child["family"], fast, slow)
            if identity not in seen:
                seen.add(identity)
                children.append(child)
            if len(children) >= MAX_CHILDREN:
                break
    return {"schema": "agent-evolution-proposals-v1", "source": "validation_guided_evolution",
            "parent_report_sha256": ancestor_hash, "proposals": children,
            "validation_diagnostics": diagnostics,
            "status": "requires_fresh_validation", "paper_only": True,
            "live_trading_authorized": False,
            "note": "不得使用 holdout 或前向結果挑選下一代；不得自動晉升或下單"}

"""Bounded feedback for model research; validation-only, no holdout leakage.

This module composes a sanitized summary of past validation evidence to ask
a caller-supplied model for a new hypothesis. It never exposes execution hooks.
"""
import json
import math
import hashlib
from agent_strategy_proposals import validate
from datetime import datetime
from agent_csv_research import read_candles
from agent_model_research import model_research

MAX_HISTORY = 12

def feedback_context(prior):
    if not isinstance(prior, dict) or prior.get("schema") != "agent-orchestrator-v1":
        raise ValueError("Invalid prior research report")
    if prior.get("paper_only") is not True or prior.get("live_trading_authorized") is not False:
        raise ValueError("Unsafe research provenance")
    candidates=prior.get("candidates")
    if not isinstance(candidates,list) or len(candidates)>MAX_HISTORY:
        raise ValueError("Invalid prior candidate count")
    summary=[]
    for item in candidates:
        if not isinstance(item,dict) or not isinstance(item.get("validation"),dict):
            raise ValueError("Invalid validation item")
        m=item["validation"]
        values={}
        for k in ("net_expectancy_r","max_drawdown_pct","trades","profit_factor"):
            v=m.get(k)
            if type(v) not in (int,float) or not math.isfinite(v):
                raise ValueError("Unusable validation metric")
            values[k]=v
        summary.append({"strategy":str(item.get("strategy",""))[:90],
                        "validation":values,"status":str(item.get("status",""))[:40]})
    return {"source":"validation_only_feedback","prior_dataset_sha256":prior.get("dataset_sha256"),
            "candidates":summary,"instruction":"Propose a *hypothesis* for independently verified new data; no code or trade instructions."}

def check_feedback_readiness(csv_path, prior, cost=0.0014):
    """Use the identical evidence checks for dry-run and real model research."""
    context=feedback_context(prior)
    if type(prior.get("cost_fraction")) not in (int, float) or prior["cost_fraction"] != cost:
        raise ValueError("Cross-generation fee assumptions must match")
    cutoff_text=prior.get("dataset_latest_utc")
    if not isinstance(cutoff_text,str):
        raise ValueError("Prior dataset cutoff missing")
    try:
        cutoff=datetime.fromisoformat(cutoff_text)
    except ValueError as exc:
        raise ValueError("Malformed prior dataset cutoff") from exc
    if cutoff.tzinfo is None or cutoff.utcoffset().total_seconds()!=0:
        raise ValueError("Prior dataset cutoff must be UTC")
    candles, dataset_hash=read_candles(csv_path)
    if dataset_hash == prior.get("dataset_sha256"):
        raise ValueError("Reused prior dataset")
    validation_start=candles[int(len(candles)*.6)][0]
    if validation_start <= cutoff:
        raise ValueError("Validation window overlaps prior research")
    return {"dataset_sha256":dataset_hash, "candles":len(candles),
            "validation_start_utc":validation_start.isoformat(),
            "parent_latest_utc":cutoff.isoformat()}

def research_with_feedback(csv_path,output_dir,model_fn,*,model_id,prior,cost=0.0014):
    check_feedback_readiness(csv_path, prior, cost)
    context=feedback_context(prior)
    def propose(prompt):
        raw = model_fn(json.dumps(context,sort_keys=True,ensure_ascii=False)+"\\n"+prompt)
        # The next generation must include a previously untested specification.
        # This compares strategy identities, not rationale text.
        if isinstance(raw,str) and len(raw.encode("utf-8")) <= 16384:
            try:
                proposals=json.loads(raw)
            except ValueError:
                return raw
            if isinstance(proposals,list) and proposals:
                seen=set()
                for item in prior["candidates"]:
                    if isinstance(item,dict) and item.get("spec") is not None:
                        seen.add(validate(item["spec"])[0])
                identities=[validate(candidate)[0] for candidate in proposals]
                if len(identities) != len(set(identities)):
                    raise ValueError("Model proposed duplicate strategies within one generation")
                if all(identity in seen for identity in identities):
                    raise ValueError("Model repeated only previously evaluated strategies")
        return raw
    # Link the model-derived candidate back to the exact parent report.
    parent_hash=hashlib.sha256(json.dumps(prior,sort_keys=True,ensure_ascii=False,allow_nan=False).encode("utf-8")).hexdigest()
    return model_research(csv_path,output_dir,propose,model_id=model_id,cost=cost,
                          parent_report_sha256=parent_hash)

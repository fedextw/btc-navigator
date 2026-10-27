"""Bounded feedback for model research; validation-only, no holdout leakage.

This module composes a sanitized summary of past validation evidence to ask
a caller-supplied model for a new hypothesis. It never exposes execution hooks.
"""
import json
import math
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

def research_with_feedback(csv_path,output_dir,model_fn,*,model_id,prior,cost=0.0014):
    context=feedback_context(prior)
    def propose(prompt):
        return model_fn(json.dumps(context,sort_keys=True,ensure_ascii=False)+"\n"+prompt)
    return model_research(csv_path,output_dir,propose,model_id=model_id,cost=cost)

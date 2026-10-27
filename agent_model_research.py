"""Strict model-proposal to offline research boundary.

A caller supplies a model function; no credentials, shell, eval or orders here.
Each JSON response is bounded and validated before entering the same research
gate as all other candidates. No LLM is configured by this module.
"""
import hashlib
import json
from agent_proposal_orchestrator import experiment, save_report
from agent_strategy_proposals import validate

MAX_RESPONSE_BYTES = 16384

def model_research(csv_path, output_dir, propose_fn, *, model_id, cost=0.0014, parent_report_sha256=None):
    if not callable(propose_fn):
        raise ValueError("A model callable is required")
    if not isinstance(model_id, str) or not 1 <= len(model_id) <= 100:
        raise ValueError("Model identifier is required")
    if parent_report_sha256 is not None and (not isinstance(parent_report_sha256,str)
            or len(parent_report_sha256)!=64
            or any(c not in "0123456789abcdef" for c in parent_report_sha256)):
        raise ValueError("Invalid parent report fingerprint")
    response = propose_fn(
        "Return a JSON array of 1-12 bounded trend/breakout candidate "
        "specifications with family, lookback, slow and rationale. "
        "No code, no executable expressions, no trading actions."
    )
    if not isinstance(response, str) or len(response.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("Oversized or invalid model response")
    candidates = json.loads(response)
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 12:
        raise ValueError("Model must return 1-12 proposals")
    for spec in candidates:
        validate(spec)
    report = experiment(csv_path, cost=cost, ai_proposals=candidates)
    report["proposal_model_id"] = model_id
    report["parent_report_sha256"] = parent_report_sha256
    report["model_feedback_used"] = parent_report_sha256 is not None
    report["model_response_sha256"] = hashlib.sha256(response.encode("utf-8")).hexdigest()
    report["proposal_execution"] = "bounded_data_only"
    report["paper_only"] = True
    report["live_trading_authorized"] = False
    path = save_report(report, output_dir)
    return {"report_path":str(path), "status":report["status"],
            "candidate_count":report["candidate_count"],"paper_only":True,
            "live_trading_authorized":False}

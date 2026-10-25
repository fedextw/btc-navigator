"""Conservative read-only stage-four acceptance audit.

Passing software unit tests is not evidence of live-data uptime, realistic fills,
or sustained profitability. Only explicit external proof can close those gates.
"""
from agent_forward_health_summary import inspect_forward_health
from agent_forward_gap_diagnostic import diagnose
from agent_forward_continuity import summarize_continuity

def audit(state_dir, *, now=None):
    health=inspect_forward_health(state_dir,now=now)
    gaps=diagnose(state_dir,max_enrollments=10)
    continuity=summarize_continuity(state_dir)
    checks={
        "periodic_health":health["status"]=="recently_completed",
        "lock_clear":health["lock"]=="unlocked",
        "stored_observation_continuity":gaps["status"]=="no_internal_gaps_detected" and gaps["checked"]>0,
        "journal_continuity":continuity["status"]=="recorded_history_only",
        "long_duration_runtime_verified":False,
        "exchange_data_freshness_verified":False,
        "recovery_drill_verified":False,
        "actual_fill_and_funding_costs_verified":False,
    }
    return {"schema":"agent-stage4-audit-v1",
            "status":"requires_more_evidence" if not all(checks.values()) else "ready_for_review",
            "checks":checks,"failed_checks":[k for k,v in checks.items() if not v],
            "health_status":health["status"],"gap_status":gaps["status"],
            "continuity_status":continuity["status"],
            "note":"此檢查不會自動宣告階段通過；長時間運作、真實行情和恢復演練須有獨立證據。",
            "paper_only":True,"live_trading_authorized":False}

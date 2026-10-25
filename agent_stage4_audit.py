"""Conservative read-only stage-four acceptance audit.

Passing software unit tests is not evidence of live-data uptime, realistic fills,
or sustained profitability. Only explicit external proof can close those gates.
"""
from agent_forward_health_summary import inspect_forward_health
from agent_forward_gap_diagnostic import diagnose
from agent_forward_continuity import summarize_continuity
from agent_stage4_runtime_window import inspect_window
from agent_stage4_market_freshness import inspect_freshness
from datetime import datetime,timezone
from pathlib import Path
import json

def audit(state_dir, *, now=None):
    health=inspect_forward_health(state_dir,now=now)
    gaps=diagnose(state_dir,max_enrollments=10)
    continuity=summarize_continuity(state_dir)
    runtime=inspect_window(state_dir,now=now or datetime.now(timezone.utc).isoformat())
    # Inspect enrolled contracts individually; the global maximum can hide
    # stale markets. A bounded enrollment scan never modifies user state.
    enrolled=[]
    folder=Path(state_dir)/"agent-forward"
    try:
        files=sorted(folder.glob("*.json")) if folder.is_dir() else []
        if len(files)>1000: raise ValueError("too many enrollments")
        for entry_path in files:
            if entry_path.stat().st_size>8192: raise ValueError("enrollment too large")
            entry=json.loads(entry_path.read_text(encoding="utf-8"))
            symbol=entry.get("symbol")
            if entry.get("schema")!="agent-forward-enrollment-v1" or entry.get("live_trading_authorized") is not False:
                raise ValueError("invalid enrollment")
            if not isinstance(symbol,str) or not symbol.endswith("USDT") or not symbol.isalnum() or len(symbol)>32:
                raise ValueError("invalid symbol")
            if symbol not in enrolled: enrolled.append(symbol)
            if len(enrolled)>30: raise ValueError("symbol audit limit")
        market=inspect_freshness(state_dir,now=now,symbols=enrolled if enrolled else None)
    except (OSError,ValueError,TypeError,KeyError):
        market={"status":"invalid_enrollment_selection","local_candle_recent":False,
                "exchange_connection_verified":False,"live_trading_authorized":False}
    # CI regression results must be supplied explicitly and cannot stand in
    # for an on-machine recovery drill or measured uptime.
    ci=Path(state_dir)/"agent-stage4-ci-evidence.json"
    ci_verified=False
    try:
        if ci.is_file() and ci.stat().st_size<=4096:
            payload=json.loads(ci.read_text(encoding="utf-8"))
            ci_verified=(payload.get("schema")=="agent-stage4-ci-v1" and
                         payload.get("windows")=="success" and
                         payload.get("linux")=="success" and
                         isinstance(payload.get("run_url"),str) and
                         payload["run_url"].startswith("https://github.com/"))
    except (OSError,ValueError,TypeError):
        pass
    drill_verified=False
    drill_file=Path(state_dir)/"agent-stage4-recovery-drill.json"
    try:
        if drill_file.is_file() and drill_file.stat().st_size<=4096:
            drill=json.loads(drill_file.read_text(encoding="utf-8"))
            expected=("preexisting_lock_preserved","exception_lock_cleanup","safe_retry","no_live_authorization")
            drill_verified=(drill.get("schema")=="agent-stage4-recovery-drill-v1" and
                            drill.get("status")=="passed" and
                            drill.get("isolated_temporary_workspace") is True and
                            drill.get("live_trading_authorized") is False and
                            isinstance(drill.get("recorded_at_utc"),str) and
                            all((drill.get("checks") or {}).get(k) is True for k in expected))
    except (OSError,ValueError,TypeError):
        pass
    checks={
        "periodic_health":health["status"]=="recently_completed",
        "lock_clear":health["lock"]=="unlocked",
        "stored_observation_continuity":gaps["status"]=="no_internal_gaps_detected" and gaps["checked"]>0,
        "journal_continuity":continuity["status"]=="recorded_history_only",
        "runtime_journal_72h_coverage":runtime.get("journal_coverage_verified") is True,
        "long_duration_runtime_verified":False,
        "local_market_candle_recent":market["local_candle_recent"] and bool(enrolled),
        "exchange_data_freshness_verified":False,
        "recovery_drill_verified":False,
        "recovery_ci_regression_reported":ci_verified,
        "isolated_local_recovery_drill_reported":drill_verified,
        "actual_fill_and_funding_costs_verified":False,
    }
    return {"schema":"agent-stage4-audit-v1",
            "status":"requires_more_evidence" if not all(checks.values()) else "ready_for_review",
            "checks":checks,"failed_checks":[k for k,v in checks.items() if not v],
            "health_status":health["status"],"gap_status":gaps["status"],
            "continuity_status":continuity["status"],
            "runtime_window_status":runtime["status"],
            "market_freshness_status":market["status"],
            "market_checked_symbols":len(enrolled),
            "ci_evidence_status":"reported" if ci_verified else "not_supplied",
            "isolated_drill_status":"reported" if drill_verified else "not_supplied",
            "note":"此檢查不會自動宣告階段通過；長時間運作、真實行情和恢復演練須有獨立證據。",
            "paper_only":True,"live_trading_authorized":False}

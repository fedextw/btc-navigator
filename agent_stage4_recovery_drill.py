"""Run an isolated recovery drill and write a local, auditable result.

No user state DB is copied, loaded, or mutated; all scenarios use TemporaryDirectory.
"""
import argparse
import json
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from agent_forward_guarded import guarded_run

def run_drill(state_dir, *, stamp=None):
    root=Path(state_dir)
    if not root.is_dir():
        raise ValueError("研究根目錄不存在")
    results={}
    with tempfile.TemporaryDirectory(prefix="stage4-recovery-") as td:
        workspace=Path(td)
        existing=workspace/"agent-forward-pipeline.lock"
        existing.write_text("external-owner",encoding="utf-8")
        blocked=guarded_run(workspace)
        results["preexisting_lock_preserved"]=(blocked.get("status")=="already_running_or_stale_lock" and existing.read_text(encoding="utf-8")=="external-owner")
        existing.unlink()  # ONLY the drill's self-created lock, never user state
        try:
            with patch("agent_forward_guarded.run_once",side_effect=RuntimeError("drill-injected-error")):
                guarded_run(workspace)
        except RuntimeError as exc:
            results["exception_lock_cleanup"]=(str(exc)=="drill-injected-error" and not existing.exists())
        else:
            results["exception_lock_cleanup"]=False
        first=guarded_run(workspace)
        second=guarded_run(workspace)
        results["safe_retry"]=(first.get("status")=="completed" and second.get("status")=="completed" and not existing.exists())
        results["no_live_authorization"]=(first.get("live_trading_authorized") is False and second.get("live_trading_authorized") is False)
    passed=all(results.values())
    at=stamp or datetime.now(timezone.utc).isoformat()
    from agent_forward_enrollment import _utc
    observed=_utc(at).isoformat()
    report={"schema":"agent-stage4-recovery-drill-v1","status":"passed" if passed else "failed",
            "recorded_at_utc":observed,"isolated_temporary_workspace":True,
            "checks":results,"live_trading_authorized":False,
            "scope":"本機隔離演練，不代表實際運行程序遭遇強制終止後已恢復"}
    destination=root/"agent-stage4-recovery-drill.json"
    with destination.open("x",encoding="utf-8") as handle:
        json.dump(report,handle,ensure_ascii=False,indent=2)
    return report

def main():
    p=argparse.ArgumentParser(description="第4階段：隔離的本機故障恢復演練，不執行交易")
    p.add_argument("--state-dir",required=True)
    args=p.parse_args()
    print(json.dumps(run_drill(args.state_dir),ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

"""Stage-six unified delivery readiness, fail-closed and read-only.

Code regression success does not substitute for 72h field operation,
live exchange provenance, failure recovery, or profitability evidence.
"""
from agent_stage4_audit import audit
from agent_stage5_batch import review_enrolled
from agent_package_integrity import verify_package
from agent_release_preflight import inspect

def inspect_delivery(state_dir, *, now=None, package_root=None):
    stage4=audit(state_dir,now=now)
    stage5=review_enrolled(state_dir,now=now)
    package_verified=(package_root is not None and verify_package(package_root)
                      and inspect(package_root)["ready"])
    research_package_ready=bool(package_verified and stage5.get("schema")=="agent-stage5-batch-v1" and stage5.get("paper_only") is True and stage5.get("live_trading_authorized") is False and stage5.get("automatic_promotion_authorized") is False)
    checks={
        "stage4_field_evidence_complete":stage4.get("status")=="ready_for_review"
            and all(stage4.get("checks",{}).values()),
        "stage5_review_data_valid":stage5.get("schema")=="agent-stage5-batch-v1"
            and stage5.get("live_trading_authorized") is False
            and stage5.get("automatic_promotion_authorized") is False,
        "strategy_candidates_reviewed":bool(stage5.get("candidates"))
            and all(c.get("decision",{}).get("status")!="hold_for_review"
                    for c in stage5.get("candidates",[])),
        "actual_exchange_execution_verified":False,
        "standalone_windows_package_verified":bool(package_verified),
    }
    return {"schema":"agent-stage6-delivery-gate-v1",
            "research_package_ready_for_manual_testing":research_package_ready,
            "research_package_status":"ready_for_manual_research_testing" if research_package_ready else "not_ready_for_manual_research_testing",
            "status":"ready_for_delivery_review" if all(checks.values())
                     else "not_ready_for_delivery",
            "checks":checks,
            "blocking_checks":[name for name,ok in checks.items() if not ok],
            "stage4_status":stage4["status"],
            "stage5_candidates_checked":stage5["checked"],
            "stage5_candidates_ranked":len(stage5["comparison"]["ranked"]),
            "live_trading_authorized":False,
            "automatic_promotion_authorized":False,
            "note":"此報告為正式交付缺口清單，絕不將 CI 綠燈視為實機或獲利驗證。"}

def main():
    import argparse
    import json
    parser=argparse.ArgumentParser(description="第六階段交付驗收（只讀、不下單）")
    parser.add_argument("--state-dir",required=True)
    parser.add_argument("--package-root",help="指定已解壓的發行包，以驗證完整性與必要模組")
    args=parser.parse_args()
    result=inspect_delivery(args.state_dir,package_root=args.package_root)
    import sys
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if args.research_only:
        return 0 if result["research_package_ready_for_manual_testing"] else 2
    return 0 if result["status"]=="ready_for_delivery_review" else 2

if __name__=="__main__":
    raise SystemExit(main())

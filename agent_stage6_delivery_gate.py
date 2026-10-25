"""Stage-six unified delivery readiness, fail-closed and read-only.

Code regression success does not substitute for 72h field operation,
live exchange provenance, failure recovery, or profitability evidence.
"""
from agent_stage4_audit import audit
from agent_stage5_batch import review_enrolled

def inspect_delivery(state_dir, *, now=None):
    stage4=audit(state_dir,now=now)
    stage5=review_enrolled(state_dir,now=now)
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
        "standalone_windows_package_verified":False,
    }
    return {"schema":"agent-stage6-delivery-gate-v1",
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
    args=parser.parse_args()
    result=inspect_delivery(args.state_dir)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["status"]=="ready_for_delivery_review" else 2

if __name__=="__main__":
    raise SystemExit(main())

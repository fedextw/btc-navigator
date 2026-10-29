"""Stage-three acceptance gate: independently verify model research evidence.

A test run is not proof of profitability. This verifier only decides whether
artifacts establish reproducible, chained, offline model research. Genuine
provider verification must be separately attested, never silently inferred.
"""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

def verify_stage_three(report_paths, *, live_provider_verified=False):
    issues=[]
    reports=[]
    if not isinstance(report_paths,(list,tuple)) or len(report_paths)<2:
        issues.append("At least two independently saved generation reports required")
    for name in report_paths:
        path=Path(name)
        try:
            raw=path.read_bytes()
            if path.suffix!=".json" or path.stem!=hashlib.sha256(raw).hexdigest():
                raise ValueError("invalid evidence digest")
            report=json.loads(raw)
            if report.get("schema")!="agent-orchestrator-v1":
                raise ValueError("wrong report schema")
            if report.get("paper_only") is not True or report.get("live_trading_authorized") is not False:
                raise ValueError("unsafe trading authorization")
            if report.get("source")!="external_ai_specifications":
                raise ValueError("no model candidate evidence")
            if not report.get("proposal_model_id") or not report.get("model_response_sha256"):
                raise ValueError("missing model proposal provenance")
            if report.get("model_feedback_used") not in (True, False):
                raise ValueError("missing model feedback provenance")
            if not isinstance(report.get("candidates"), list) or not 1 <= len(report["candidates"]) <= 12:
                raise ValueError("invalid candidate evidence")
            if report.get("candidate_count") != len(report["candidates"]):
                raise ValueError("candidate evidence count mismatch")
            if any(not isinstance(item, dict) or item.get("status") not in ("rejected", "validation_pass")
                   for item in report["candidates"]):
                raise ValueError("invalid candidate evaluation status")
            for label in ("validation_start_utc", "dataset_latest_utc"):
                stamp=datetime.fromisoformat(report[label])
                if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
                    raise ValueError("invalid UTC research interval")
            if report["validation_start_utc"] >= report["dataset_latest_utc"]:
                raise ValueError("invalid validation interval")
            if type(report.get("cost_fraction")) not in (int, float) or not 0 <= report["cost_fraction"] <= .1:
                raise ValueError("invalid research cost")
            if report.get("selected") is not None and not any(
                item["strategy"] == report["selected"] and item["status"] == "validation_pass"
                for item in report["candidates"]):
                raise ValueError("unqualified strategy selected")
            reports.append(report)
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            issues.append("Invalid generation report: "+str(exc))
            break
    for earlier,later in zip(reports,reports[1:]):
        expected=hashlib.sha256(json.dumps(earlier,sort_keys=True,ensure_ascii=False,
                                           allow_nan=False).encode("utf-8")).hexdigest()
        if later.get("parent_report_sha256")!=expected or later.get("model_feedback_used") is not True:
            issues.append("Broken intergeneration parent lineage")
        if later.get("validation_start_utc","")<=earlier.get("dataset_latest_utc",""):
            issues.append("Overlapping chronological validation evidence")
        if earlier.get("cost_fraction")!=later.get("cost_fraction"):
            issues.append("Inconsistent trading-cost assumptions")
        if earlier.get("proposal_model_id")!=later.get("proposal_model_id"):
            issues.append("Mixed model provenance inside single research lineage")
        if earlier.get("dataset_sha256")==later.get("dataset_sha256"):
            issues.append("Reused dataset in research lineage")
    if not live_provider_verified:
        issues.append("Live LLM provider end-to-end verification outstanding")
    return {"schema":"agent-stage-three-acceptance-v1",
            "accepted":not issues,"issues":issues,
            "verified_reports":len(reports),
            "live_trading_authorized":False,"paper_only":True}

def main():
    parser=argparse.ArgumentParser(description="Verify stage-three research evidence")
    parser.add_argument("reports",nargs="+")
    parser.add_argument("--provider-verified",action="store_true",
                        help="Explicit external attestation; not checked by this command")
    args=parser.parse_args()
    result=verify_stage_three(args.reports,live_provider_verified=args.provider_verified)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result["accepted"]:
        raise SystemExit(2)

if __name__=="__main__":
    main()

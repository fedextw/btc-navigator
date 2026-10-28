"""Stage-four local acceptance: read-only preflight or explicitly billed live batch.

No CI invocation of live APIs, credentials, order routing or promotion.
"""
import argparse
import json
import os
from pathlib import Path
from agent_stage_four_rotation import run_rotation
from agent_stage_four_integrated_audit import audit_delivery

def delivery(state_dir, *, slot, execute=False, allow_model_calls=0,
             interval="1h",model="gpt-4.1-mini",count=1600,
             fetch=None,runner=None):
    if execute:
        # Rotation currently selects up to 10 markets with one model call
        # apiece. Explicitly acknowledge that upper bound before any I/O.
        if type(allow_model_calls) is not int or allow_model_calls!=10:
            raise ValueError("Executing full rotation requires --allow-model-calls 10")
        if not os.getenv("OPENAI_API_KEY") and runner is None:
            raise ValueError("OPENAI_API_KEY missing; no market request made")
        rotation=run_rotation(state_dir,slot=slot,interval=interval,
                             model=model,count=count,fetch=fetch,runner=runner)
    else:
        rotation={"status":"not_executed","paper_only":True,
                  "live_trading_authorized":False}
    # A provider or injected rotation must explicitly prove it did not
    # authorize live orders. Never certify an unsafe/unknown response.
    if (rotation.get("paper_only") is not True or
            rotation.get("live_trading_authorized") is not False or
            rotation.get("status") not in (
                "completed","already_processed","waiting_for_fresh_data",
                "requires_manual_review","empty_universe","not_executed")):
        raise ValueError("Unsafe or unrecognized Stage Four acceptance result")
    audit=audit_delivery(state_dir,interval=interval)
    return {"schema":"agent-stage4-local-acceptance-v1",
            "mode":"live_public_data_and_model" if execute else "offline_preflight",
            "rotation_status":rotation["status"],"rotation":rotation,
            "audit":audit,"engineering_evidence_valid":audit["engineering_evidence_valid"],
            "real_forward_paper_validated":False,
            "profitability_proven":False,"automatic_promotion":False,
            "paper_only":True,"live_trading_authorized":False}

def main():
    p=argparse.ArgumentParser(description="Stage-four offline preflight or explicitly billed public-market AI trial")
    p.add_argument("--state-dir",required=True)
    p.add_argument("--slot",required=True)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--allow-model-calls",type=int,default=0)
    p.add_argument("--interval",default="1h")
    p.add_argument("--model",default="gpt-4.1-mini")
    p.add_argument("--count",type=int,default=1600)
    args=p.parse_args()
    # Refuse destination collisions BEFORE any potentially billable model I/O.
    out=Path(args.state_dir)/("stage4-live-acceptance.json" if args.execute
                              else "stage4-preflight.json")
    if out.exists():
        p.error("Acceptance summary already exists; use a new state directory")
    result=delivery(args.state_dir,slot=args.slot,execute=args.execute,
       allow_model_calls=args.allow_model_calls,interval=args.interval,
       model=args.model,count=args.count)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf-8") as handle:
        json.dump(result,handle,ensure_ascii=False,sort_keys=True,
                  indent=2,allow_nan=False)
        handle.write("\n")
    print(json.dumps({"summary_path":str(out),"result":result},
                     ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()

"""Offline integration audit of a complete stage-four research rotation.

This is a read-only certification of saved evidence, not a simulated market
performance claim. It requires both rotation completion and intact per-market
reports before a batch can be considered engineering-complete.
"""
import argparse
import json
from pathlib import Path
from agent_stage_four_paper_review import review

def audit_delivery(state_dir, *, papers=None, interval="1h"):
    state=Path(state_dir)
    rotation=state/"stage4-universe-cursor.json"
    issues=[]
    if not rotation.is_file():
        issues.append("missing_rotation_checkpoint")
        cursor=None
    else:
        if rotation.stat().st_size>4096:
            raise ValueError("Oversized rotation checkpoint")
        cursor=json.loads(rotation.read_text(encoding="utf-8"))
        if (cursor.get("schema")!="agent-stage4-universe-cursor-v1"
                or cursor.get("paper_only") is not True
                or cursor.get("live_trading_authorized") is not False
                or cursor.get("status")!="completed"):
            issues.append("rotation_not_completed")
    evidence=review(state,paper_summaries=papers,interval=interval)
    # Bind audit to the actual market selection for THIS rotation slot.
    if cursor is not None and cursor.get("status")=="completed":
        expected=cursor.get("symbols")
        if (not isinstance(expected,list) or not expected
                or len(expected)>10 or len(expected)!=len(set(expected))
                or any(not isinstance(x,str) for x in expected)):
            issues.append("rotation_market_selection_missing")
        else:
            by_symbol={x["symbol"]:x for x in evidence["markets"]}
            if any(symbol not in by_symbol or
                   by_symbol[symbol]["slot"]!=cursor["slot"] or
                   not by_symbol[symbol]["report_verified"]
                   for symbol in expected):
                issues.append("rotation_market_evidence_mismatch")
    if evidence["research_reports_verified"]==0:
        issues.append("no_verified_research_reports")
    if any(x["checkpoint_status"]!="completed" or not x["report_verified"]
           for x in evidence["markets"]):
        issues.append("incomplete_market_research")
    return {"schema":"agent-stage4-integrated-audit-v1",
            "engineering_evidence_valid":not issues,
            "issues":issues,"rotation_slot":cursor.get("slot") if cursor else None,
            "markets_checked":len(evidence["markets"]),
            "reports_verified":evidence["research_reports_verified"],
            "prospective_paper_markets":evidence["prospective_paper_markets"],
            "forward_performance_validated":False,
            "profitability_proven":False,"automatic_promotion":False,
            "paper_only":True,"live_trading_authorized":False}

def main():
    p=argparse.ArgumentParser(description="Read-only stage-four integrated research evidence audit")
    p.add_argument("--state-dir",required=True)
    p.add_argument("--interval",default="1h")
    p.add_argument("--papers",help="Optional JSON map SYMBOL to prospective paper summary")
    a=p.parse_args()
    mapping=json.loads(Path(a.papers).read_text(encoding="utf-8")) if a.papers else None
    print(json.dumps(audit_delivery(a.state_dir,papers=mapping,interval=a.interval),
                     ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()

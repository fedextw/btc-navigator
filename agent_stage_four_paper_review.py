"""Audit stage-four research against independent prospective paper summaries.

A positive research validation score cannot be silently substituted for
out-of-sample forward performance. No auto-promotion or trading permissions.
"""
import argparse
import hashlib
import json
from pathlib import Path
from agent_stage_four_evidence import inspect

def review(state_dir, *, paper_summaries=None, interval="1h"):
    research=inspect(state_dir,interval=interval)
    papers=paper_summaries or {}
    if not isinstance(papers,dict): raise ValueError("Invalid paper summary mapping")
    result=[]
    for market in research["markets"]:
        symbol=market["symbol"]
        entry=dict(market,forward_evidence="not_submitted",
                   observed_forward_trades=0,profitability_proven=False)
        source=papers.get(symbol)
        if source is not None:
            path=Path(source)
            if path.stat().st_size>2_000_000:
                raise ValueError("Oversized paper summary")
            paper=json.loads(path.read_text(encoding="utf-8"))
            if (paper.get("schema")!="agent-forward-paper-v1" or
                    paper.get("symbol")!=symbol or
                    paper.get("live_trading_authorized") is not False or
                    paper.get("not_actual_fills") is not True or
                    paper.get("execution_verified") is not False):
                raise ValueError("Incompatible or unsafe paper evidence")
            trades=paper.get("prospective_eligible_trades")
            if type(trades) is not int or trades<0:
                raise ValueError("Invalid prospective paper sample count")
            if market["report_verified"]:
                check=Path(state_dir)/"markets"/symbol/interval/"stage4-checkpoint.json"
                checkpoint=json.loads(check.read_text(encoding="utf-8"))
                report_sha=hashlib.sha256(Path(checkpoint["report_path"]).read_bytes()).hexdigest()
                if paper.get("research_sha256")!=report_sha:
                    raise ValueError("Paper evidence references another research report")
            else:
                raise ValueError("Paper results cannot be attached to incomplete research")
            entry.update(forward_evidence=paper.get("evidence_status","unreviewed"),
                         observed_forward_trades=trades,
                         prospective_paper_net_return_pct=paper.get("prospective_paper_net_return_pct"),
                         execution_verified=False)
        result.append(entry)
    return {"schema":"agent-stage4-paper-review-v1","markets":result,
            "research_reports_verified":research["verified_reports"],
            "prospective_paper_markets":sum(x["observed_forward_trades"]>0 for x in result),
            "profitability_proven":False,"automatic_promotion":False,
            "paper_only":True,"live_trading_authorized":False}

def main():
    p=argparse.ArgumentParser(description="Stage-four research/forward-paper evidence audit")
    p.add_argument("--state-dir",required=True)
    p.add_argument("--papers",help="JSON object: SYMBOL to forward paper JSON path")
    p.add_argument("--interval",default="1h")
    a=p.parse_args()
    mapping=json.loads(Path(a.papers).read_text(encoding="utf-8")) if a.papers else {}
    print(json.dumps(review(a.state_dir,paper_summaries=mapping,interval=a.interval),
                     ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()

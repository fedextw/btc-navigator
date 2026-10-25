"""Stage five: one bounded research-to-review orchestration, paper only.

Runs the existing research batch, then evaluates recorded forward evidence.
No automatic promotion, strategy code generation or live orders.
"""
import argparse
import json
from agent_research_scheduler import run_once
from agent_stage5_batch import review_enrolled, save_review_snapshot

def run_research_review(state_dir, *, symbols, now=None, save=False,
                        research_runner=None, review_runner=review_enrolled):
    if research_runner is None:
        research_runner=run_once
    research=research_runner(state_dir,symbols=tuple(symbols),interval="1h",mode="live")
    if (not isinstance(research,dict) or research.get("schema")!="agent-scheduler-v1"
            or research.get("live_trading_authorized") is not False
            or research.get("paper_only") is not True):
        raise ValueError("研究批次不符合安全條件")
    decisions=review_runner(state_dir,now=now)
    if (not isinstance(decisions,dict) or decisions.get("schema")!="agent-stage5-batch-v1"
            or decisions.get("automatic_promotion_authorized") is not False
            or decisions.get("live_trading_authorized") is not False):
        raise ValueError("審查批次不符合安全條件")
    result={"schema":"agent-stage5-cycle-v1","research":research,
            "review":decisions,"automatic_promotion_authorized":False,
            "live_trading_authorized":False,"paper_only":True,
            "note":"受控研究與前向審查；尚非自主產生策略或授權實盤"}
    if save:
        path=save_review_snapshot(state_dir,decisions)
        result["review_snapshot"]=str(path)
    return result

def main():
    parser=argparse.ArgumentParser(description="第五階段受控研究循環，不進行真實下單")
    parser.add_argument("--state-dir",required=True)
    parser.add_argument("--symbols",nargs="+",required=True)
    parser.add_argument("--save-review",action="store_true")
    args=parser.parse_args()
    print(json.dumps(run_research_review(args.state_dir,symbols=args.symbols,
                                          save=args.save_review),ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

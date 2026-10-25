"""Stage five: one bounded research-to-review orchestration, paper only.

Runs the existing research batch, then evaluates recorded forward evidence.
No automatic promotion, strategy code generation or live orders.
"""
import argparse
import json
from agent_research_scheduler import run_once
from agent_stage5_batch import review_enrolled, save_review_snapshot
from agent_research_universe import next_batch

def run_research_review(state_dir, *, symbols=None, now=None, save=False,
                        batch_number=0, universe_runner=next_batch,
                        research_runner=None, review_runner=review_enrolled):
    if research_runner is None:
        research_runner=run_once
    # Auto-universe reads only contiguous local USDT research data.
    if symbols is None:
        symbols=universe_runner(state_dir,"1h","live",batch_number=batch_number)
    if not symbols:
        return {"schema":"agent-stage5-cycle-v1","status":"waiting_for_research_ready_symbols",
                "automatic_promotion_authorized":False,"live_trading_authorized":False,
                "paper_only":True}
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
    parser.add_argument("--symbols",nargs="+",help="指定標的；省略則輪替研究本機已就緒 USDT 合約")
    parser.add_argument("--batch-number",type=int,default=0)
    parser.add_argument("--save-review",action="store_true")
    args=parser.parse_args()
    print(json.dumps(run_research_review(args.state_dir,symbols=args.symbols,batch_number=args.batch_number,
                                          save=args.save_review),ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

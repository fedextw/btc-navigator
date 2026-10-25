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

def run_rotation(state_dir, *, rounds=3, start_batch=0, cycle_runner=run_research_review):
    """Bounded multi-batch research; no hidden daemon or trading."""
    if type(rounds) is not int or not 1<=rounds<=10 or type(start_batch) is not int or start_batch<0:
        raise ValueError("研究輪次不合法")
    results=[]
    for index in range(rounds):
        item=cycle_runner(state_dir,batch_number=start_batch+index)
        if (not isinstance(item,dict) or item.get("schema")!="agent-stage5-cycle-v1"
                or item.get("live_trading_authorized") is not False
                or item.get("automatic_promotion_authorized") is not False):
            raise ValueError("輪替研究結果不符合安全要求")
        results.append(item)
        if item.get("status")=="waiting_for_research_ready_symbols":
            break
    return {"schema":"agent-stage5-rotation-v1","cycles":results,
            "completed_cycles":sum("research" in item for item in results),
            "automatic_promotion_authorized":False,"live_trading_authorized":False,
            "paper_only":True}

def main():
    parser=argparse.ArgumentParser(description="第五階段受控研究循環，不進行真實下單")
    parser.add_argument("--state-dir",required=True)
    parser.add_argument("--symbols",nargs="+",help="指定標的；省略則輪替研究本機已就緒 USDT 合約")
    parser.add_argument("--batch-number",type=int,default=0)
    parser.add_argument("--save-review",action="store_true")
    parser.add_argument("--rounds",type=int,default=1,help="輪替研究最多10批；不會常駐或自動下單")
    args=parser.parse_args()
    if args.rounds==1:
        report=run_research_review(args.state_dir,symbols=args.symbols,batch_number=args.batch_number,
                                   save=args.save_review)
    else:
        if args.symbols or args.save_review:
            parser.error("多批輪替僅適用動態標的池且不寫入審查快照")
        report=run_rotation(args.state_dir,rounds=args.rounds,start_batch=args.batch_number)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

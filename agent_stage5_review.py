"""Stage 5: bounded, manual-review-only candidate promotion decision.

Never runs strategies, installs code, changes production configuration,
or grants live-trading authority. The stage-four field acceptance remains open.
"""
import math
from agent_stage4_audit import audit

def review_candidate(state_dir, paper, *, now=None, minimum_samples=30):
    if type(minimum_samples) is not int or not 30<=minimum_samples<=10000:
        raise ValueError("研究樣本門檻不合法")
    acceptance=audit(state_dir,now=now)
    reasons=[]
    if not isinstance(paper,dict) or paper.get("schema")!="agent-forward-paper-v1":
        reasons.append("前向研究報告格式不合法")
        paper={}
    if paper.get("live_trading_authorized") is not False or paper.get("not_actual_fills") is not True:
        reasons.append("前向研究未明確限制為紙上模擬")
    samples=paper.get("prospective_eligible_trades")
    if type(samples) is not int or samples<minimum_samples:
        reasons.append("及時觀測前向樣本不足")
    if type(paper.get("retrospective_only_trades")) is not int or paper["retrospective_only_trades"]<0:
        reasons.append("缺少事後觀測分流證據")
    for key in ("prospective_paper_net_return_pct","prospective_paper_expectancy_fraction"):
        val=paper.get(key)
        if type(val) not in (int,float) or not math.isfinite(val) or val<=0:
            reasons.append("前向淨績效或期望值不符合條件")
            break
    dd=paper.get("prospective_paper_max_drawdown_pct")
    if type(dd) not in (float,int) or not math.isfinite(dd) or dd<0 or dd>=12:
        reasons.append("前向最大回撤不符合研究門檻")
    pf=paper.get("prospective_paper_profit_factor")
    if type(pf) not in (float,int) or not math.isfinite(pf) or pf<1.15:
        reasons.append("前向獲利因子不足或不可驗證")
    if not all(acceptance["checks"].values()):
        reasons.append("第四階段實際環境驗收證據尚未齊全")
    return {"schema":"agent-stage5-review-v1",
            "status":"hold_for_review" if reasons else "eligible_for_manual_paper_review",
            "reasons":reasons,
            "stage4_status":acceptance["status"],
            "samples":samples if type(samples) is int else 0,
            "automatic_promotion_authorized":False,
            "live_trading_authorized":False,
            "paper_only":True}

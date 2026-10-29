import unittest
from agent_stage5_ranking import rank_candidates

def candidate(symbol,dd,pf,ret,approved=True):
    return {"symbol":symbol,"strategy":"trend_8_30","research_sha256":symbol,
            "decision":{"status":"eligible_for_manual_paper_review" if approved else "hold_for_review"},
            "paper_evidence":{"prospective_eligible_trades":40,
                "prospective_paper_net_return_pct":ret,
                "prospective_paper_profit_factor":pf,
                "prospective_paper_max_drawdown_pct":dd}}

class StageFiveRankingTests(unittest.TestCase):
    def test_risk_first_ranking_never_includes_rejected(self):
        result=rank_candidates([candidate("BTCUSDT",4,1.6,3),
                                candidate("ETHUSDT",2,1.3,2),
                                candidate("SOLUSDT",1,5,30,False)])
        self.assertEqual([x["symbol"] for x in result["ranked"]],["ETHUSDT","BTCUSDT"])
        self.assertEqual([x["rank"] for x in result["ranked"]],[1,2])
        self.assertFalse(result["automatic_promotion_authorized"])
        self.assertFalse(result["live_trading_authorized"])
    def test_missing_or_invalid_metrics_fail_closed(self):
        item=candidate("BTCUSDT",3,1.5,4)
        item["paper_evidence"]["prospective_paper_profit_factor"]=float("nan")
        self.assertEqual(rank_candidates([item])["ranked"],[])
        item["paper_evidence"]["prospective_paper_profit_factor"]=1.7
        item["paper_evidence"]["prospective_eligible_trades"]=3
        self.assertEqual(rank_candidates([item])["ranked"],[])
    def test_empty_list_safe(self):
        self.assertEqual(rank_candidates([])["ranked"],[])

if __name__=="__main__":
    unittest.main()

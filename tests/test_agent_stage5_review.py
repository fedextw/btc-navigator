import tempfile
import unittest
from unittest.mock import patch
from agent_stage5_review import review_candidate

class Stage5ReviewTests(unittest.TestCase):
    def paper(self):
        return {"schema":"agent-forward-paper-v1","not_actual_fills":True,
                "live_trading_authorized":False,"prospective_eligible_trades":40,
                "retrospective_only_trades":3,
                "prospective_paper_net_return_pct":4.2,
                "prospective_paper_expectancy_fraction":0.001,
                "prospective_paper_max_drawdown_pct":4.5,
                "prospective_paper_profit_factor":1.6}
    def test_good_paper_metrics_do_not_bypass_stage4_field_gates(self):
        with tempfile.TemporaryDirectory() as td:
            result=review_candidate(td,self.paper(),now="2026-10-26T10:00:00Z")
            self.assertEqual(result["status"],"hold_for_review")
            self.assertFalse(result["automatic_promotion_authorized"])
            self.assertFalse(result["live_trading_authorized"])
            self.assertIn("第四階段實際環境驗收證據尚未齊全",result["reasons"])
    def test_even_approved_evidence_means_paper_manual_review_only(self):
        fake={"status":"ready_for_review","checks":{"runtime":True,"market":True}}
        with patch("agent_stage5_review.audit",return_value=fake):
            result=review_candidate("/unused",self.paper())
        self.assertEqual(result["status"],"eligible_for_manual_paper_review")
        self.assertFalse(result["automatic_promotion_authorized"])
        self.assertFalse(result["live_trading_authorized"])
    def test_retrospective_or_bad_metrics_fail_closed(self):
        p=self.paper()
        p["prospective_eligible_trades"]=0
        p["prospective_paper_net_return_pct"]=None
        fake={"status":"ready_for_review","checks":{"runtime":True}}
        with patch("agent_stage5_review.audit",return_value=fake):
            result=review_candidate("/unused",p)
        self.assertEqual(result["status"],"hold_for_review")
        self.assertGreaterEqual(len(result["reasons"]),2)

if __name__=="__main__":
    unittest.main()

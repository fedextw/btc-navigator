import json
import tempfile
import unittest
from pathlib import Path
from agent_research_gate import assess, review_file


def example():
    return dict(
        hypothesis="Breakout candidate, research only", dataset_fingerprint="sha256:test",
        code_commit="abc123", train_end_utc="2026-01-01T00:00:00Z",
        test_start_utc="2026-02-01T00:00:00Z", test_end_utc="2026-05-01T00:00:00Z",
        trades=120, trading_days=35, net_expectancy_r=0.08, max_drawdown_pct=9.0,
        profit_factor=1.18, costs_included=True, lookahead_checked=True,
        heldout_untouched=True, paper_only=True)


class ResearchGateTests(unittest.TestCase):
    def test_eligible_never_authorizes_trades(self):
        result = assess(example())
        self.assertEqual(result["status"], "eligible_for_independent_review")
        self.assertFalse(result["live_trading_authorized"])

    def test_missing_data_fails_closed(self):
        p = example()
        p.pop("costs_included")
        self.assertEqual(assess(p)["status"], "rejected")

    def test_bad_evidence_fails_closed(self):
        for field, value in [("heldout_untouched", False), ("trades", 20),
                             ("net_expectancy_r", -0.1), ("paper_only", False)]:
            p = example()
            p[field] = value
            self.assertEqual(assess(p)["status"], "rejected")

    def test_future_data_boundary(self):
        p = example()
        p["test_start_utc"] = p["train_end_utc"]
        self.assertEqual(assess(p)["status"], "rejected")

    def test_nan_and_coerced_types_rejected(self):
        for field, value in [("profit_factor", float("nan")),
                             ("trades", True), ("costs_included", 1)]:
            p = example()
            p[field] = value
            with self.assertRaises(ValueError):
                assess(p)

    def test_immutable_audit_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "proposal.json"
            src.write_text(json.dumps(example()), encoding="utf-8")
            audit = Path(directory) / "audit"
            a = review_file(src, audit)
            b = review_file(src, audit)
            self.assertEqual(a, b)
            self.assertEqual(len(list(audit.glob("*.json"))), 1)
            self.assertFalse(a["live_trading_authorized"])


if __name__ == "__main__":
    unittest.main()

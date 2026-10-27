import unittest
from agent_recheck_comparison import compare_research_recheck

class RecheckComparisonTests(unittest.TestCase):
    def test_bad_fingerprint_rejected(self):
        with self.assertRaises(ValueError):
            compare_research_recheck('.', 'invalid', {'live_trading_authorized':False})

if __name__ == '__main__':
    unittest.main()

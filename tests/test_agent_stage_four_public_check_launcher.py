import unittest
from pathlib import Path
from agent_release_preflight import ESSENTIAL

class PublicCandleWindowsLauncherTests(unittest.TestCase):
    def test_public_diagnostic_is_part_of_release(self):
        root=Path(__file__).resolve().parents[1]
        self.assertIn("CHECK_BC_PUBLIC_CANDLES.bat",ESSENTIAL)
        source=(root/"CHECK_BC_PUBLIC_CANDLES.bat").read_text(encoding="utf-8")
        self.assertIn("agent_stage_four_candle_preflight.py --symbol 4USDT",source)
        self.assertNotIn("--openai-batches",source)
        self.assertNotIn("OPENAI_API_KEY",source)
if __name__=="__main__":unittest.main()

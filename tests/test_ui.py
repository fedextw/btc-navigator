"""Exercise navigation and scenario controls with an isolated demo state."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class TerminalUITests(unittest.TestCase):
    def test_five_workspaces_and_cost_scenario_without_external_services(self):
        with tempfile.TemporaryDirectory() as state:
            env={**os.environ,'BTC_NAVIGATOR_STATE_DIR':state,'BTC_NAVIGATOR_DEMO':'1'}
            script='''
from streamlit.testing.v1 import AppTest
at=AppTest.from_file('btc_app.py',default_timeout=30).run()
assert not at.exception, at.exception
assert not any(x.label=='交易對' for x in at.selectbox)
for page in ['學習與績效','系統健康','設定中心','單幣研究','全市場訊號']:
    next(x for x in at.radio if x.label=='功能').set_value(page).run()
    assert not at.exception, (page,at.exception)
    if page=='設定中心':
        assert next(x for x in at.selectbox if x.label=='文字 AI 供應者').value=='ollama'
    if page=='單幣研究':
        assert any(x.label=='交易對' for x in at.selectbox)
next(x for x in at.radio if x.label=='功能').set_value('學習與績效').run()
next(x for x in at.button if x.label=='計算資金與成本情境').click().run()
assert not at.exception,at.exception
assert next(x for x in at.metric if x.label=='情境期末資金').value=='10,000.00'
print('UI_SMOKE_PASS')
'''
            result=subprocess.run([sys.executable,'-c',script],cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('UI_SMOKE_PASS',result.stdout)

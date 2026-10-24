"""Exercise navigation and scenario controls with an isolated demo state."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class TerminalUITests(unittest.TestCase):
    def test_workspaces_charts_walk_forward_and_cost_scenario_without_external_services(self):
        with tempfile.TemporaryDirectory() as state:
            env={**os.environ,'BTC_NAVIGATOR_STATE_DIR':state,'BTC_NAVIGATOR_DEMO':'1'}
            script='''
from streamlit.testing.v1 import AppTest
at=AppTest.from_file('btc_app.py',default_timeout=30).run()
assert not at.exception, at.exception
assert any(x.label=='查詢交易對' for x in at.selectbox)
assert not any(x.label=='功能' for x in at.radio)
assert not any(x.label=='OpenAI API Key' for x in at.text_input)
for front_page in ['行情查詢','自選清單']:
    next(x for x in at.radio if x.label=='前台功能').set_value(front_page).run()
    assert not at.exception,at.exception
next(x for x in at.multiselect if x.label=='管理自選合約').set_value(['BTCUSDT']).run()
next(x for x in at.button if x.label=='儲存自選清單').click().run()
assert not at.exception,at.exception
from pathlib import Path
assert Path(__import__('os').environ['BTC_NAVIGATOR_STATE_DIR']).joinpath('frontend-watchlist.json').exists()
next(x for x in at.radio if x.label=='介面').set_value('研究後台').run()
assert not at.exception,at.exception
assert not any(x.label=='交易對' for x in at.selectbox)
# Status updates have a different payload from entry alerts; old workspaces must render both.
import json,time
from signal_store import connect as event_db
edb=event_db();stamp=time.time()
event={'kind':'strategy_lifecycle','trade_id':'ui-test','lifecycle_id':1,'base_event_id':'mock','symbol':'BTCUSDT','interval':'1h','strategy':'trend','side':'LONG','state':'closed','observed_at':'2026-10-24 00:00:00+00:00','effective_at':None,'details':{'reason':'合成介面測試'},'pnl':-1.,'mode':'live'}
edb.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('ui-lifecycle',stamp,stamp+600,'BTCUSDT','1h','LONG','live',json.dumps(event)));edb.commit();edb.close()
for page in ['策略訊號台','互動決策台','學習與績效','系統健康','設定中心','單幣研究','全市場訊號']:
    next(x for x in at.radio if x.label=='功能').set_value(page).run()
    assert not at.exception, (page,at.exception)
    if page=='策略訊號台':
        assert any('AI強化實驗室' in x.value for x in at.markdown)
        assert any('交易錯誤歸因與改善觀察' in x.value for x in at.markdown)
        assert next(x for x in at.metric if x.label=='AI選擇後平均淨報酬').value=='尚無樣本'
        assert any(x.label=='已封存策略模型' for x in at.metric)
        assert not any(x.label=='目標勝率' for x in at.metric)
        assert next(x for x in at.metric if x.label=='AI選擇後未來觀察勝率').value=='尚無樣本'
        next(x for x in at.button if x.label=='執行此策略歷史重播').click().run(timeout=45)
        assert not at.exception,at.exception
        assert any(x.label=='歷史重播交易' for x in at.metric)
        assert next(x for x in at.metric if x.label=='已結算策略交易').value=='0'
    if page=='互動決策台':
        assert next(x for x in at.metric if x.label=='背景原訊號').value=='WAIT'
        next(x for x in at.slider if x.label=='顯示最近 K 線根數').set_value(120).run()
        next(x for x in at.checkbox if x.label=='顯示 EMA').uncheck().run()
        next(x for x in at.button if x.label=='執行三段滾動驗證').click().run(timeout=45)
        assert not at.exception,at.exception
        assert any(x.label=='未見測試交易' for x in at.metric)
        assert next(x for x in at.selectbox if x.label=='滾動報告來源').value=='手動研究副本'
        from pathlib import Path
        assert list(Path(__import__('os').environ['BTC_NAVIGATOR_STATE_DIR']).joinpath('walk-research').glob('*.json'))
    if page=='全市場訊號':
        assert any('狀態更新' in x.label for x in at.expander)
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

"""Live valuation is deliberately separate from immutable realized strategy capital."""
import json
import time
import pandas as pd
import streamlit as st
from runtime_config import STATE_ROOT
from risk_worker import quotes
from strategy_risk import value_positions,correlation_pairs
from signal_store import connect
from terminal_ui import section


def live_risk_panel(stats,mode):
    section('即時持倉風險雷達','MARK PRICE / EXPOSURE / DATA QUALITY')
    q,raw=quotes(STATE_ROOT,mode=mode)
    report=value_positions(stats['rows'],stats['account'],q)
    a,b,c,d=st.columns(4)
    a.metric('估計浮動淨損益',f'{report["floating"]:+,.2f} USDT' if report['floating'] is not None else '未知／報價不足')
    b.metric('估計總權益',f'{report["estimated_equity"]:,.2f} USDT' if report['estimated_equity'] is not None else '尚未建立／未知')
    c.metric('此策略名目曝險',f'{report["gross_exposure"]:,.2f} USDT' if report['gross_exposure'] is not None else '部分未知')
    d.metric('可估部位方向集中度',f'{report["direction_concentration_pct"]:.1f}%' if report['direction_concentration_pct'] is not None else '無可估持倉')
    if raw.get('updated_at'):
        age=max(0,int(time.time()-raw['updated_at']))
        st.caption(f'風險報價心跳 {age} 秒前 · 逐幣按交易所時間檢查120秒有效期；不是成交保證。')
        if age>120:st.warning('風險報價更新過期，不能依賴上次浮盈虧。')
    else:st.info('尚無風險報價。請用新版啟動檔保持背景運作；示範模式不啟動公開報價收集。')
    if raw.get('error'):st.warning('部分公開報價收集失敗：'+raw['error']+'；缺少資料不會假裝新鮮。')
    if report['unknown']:st.error(f'{report["unknown"]} 個部位無法可靠估值；總權益與總曝險不填0，已知部位仍可逐筆查看。')
    st.caption('本區只估所選策略；趨勢與當沖使用獨立紙上帳戶。'+report['note'])
    if report['positions']:st.dataframe(pd.DataFrame(report['positions']),hide_index=True,width='stretch')
    frames={};db=connect(STATE_ROOT)
    try:
        for symbol in {r['symbol'] for r in stats['rows'] if r['status']=='open'}:
            row=db.execute('SELECT payload FROM scan_cache WHERE symbol=? AND interval=? AND mode=?',(symbol,'1h',mode)).fetchone()
            if row:frames[symbol]=pd.DataFrame(json.loads(row[0]))
    finally:db.close()
    pairs=correlation_pairs(stats['rows'],frames)
    with st.expander('持倉關聯與共同方向風險'):
        st.caption('同一策略開倉部位：最近最多120根完整1h報酬，至少30個對齊樣本，最後收盤不超過2小時。方向調整相關≥0.8提醒可能押同一市場方向；不是未來相關保證，不宣稱已做組合限額。')
        if pairs:st.dataframe(pd.DataFrame(pairs),hide_index=True,width='stretch')
        else:st.caption('不足兩個可比較持倉或缺少連續新鮮行情，尚無相關估計。')

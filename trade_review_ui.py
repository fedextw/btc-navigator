"""Explain measurements and uncertainty without inventing causal AI diagnoses."""
import json
import pandas as pd
import streamlit as st
from trade_review import review,LABELS
from signal_lifecycle import KINDS
from terminal_ui import section


def review_panel(db,profile,mode,rows):
    section('交易錯誤歸因與改善觀察','MEASUREMENTS / NOT CAUSAL PROOF')
    closed=[r for r in rows if r['status']=='closed'];losses=[r for r in closed if r.get('pnl',0)<0]
    reports=[r.get('post_trade_review') or review(r) for r in losses]
    a,b,c=st.columns(3);a.metric('待復盤虧損交易',len(losses));b.metric('可重建完整成本',sum(r['bridge'] is not None for r in reports));c.metric('完整路徑觀察',sum(r.get('path_complete',False) for r in reports))
    st.caption('標籤可重疊，不把各類損益相加；描述已觀測現象，不證明止損設錯、進場太晚或新聞造成虧損。舊紀錄缺欄位時不補造。')
    counts=[{'觀察標籤':name,'虧損筆數':sum(key in r['tags'] for r in reports)} for key,name in LABELS.items()]
    st.dataframe(pd.DataFrame(counts),hide_index=True,width='stretch')
    with st.expander('這些觀察下一步怎麼驗證'):
        st.write('成本轉負：比較費率、價差與風報比篩選；開盤偏移：研究有效期限與追價限制；有利後虧損：另做移動止損／部分止盈的影子實驗；同根雙觸：優先補更細週期資料。')
        st.caption('以上只列待驗證方向，不自動修改任何策略、模型門檻或既有損益。')


def timeline(db,t):
    section('訊號生命週期','OBSERVED TIME / MODELED EVENT TIME')
    events=db.execute('SELECT * FROM strategy_lifecycle WHERE trade_id=? ORDER BY id',(t['id'],)).fetchall()
    if events:
        st.dataframe(pd.DataFrame([{'階段':KINDS.get(e['kind'],e['kind']),'實際確認UTC':e['observed_at'],'事件／預定期限UTC':e['effective_at'],'說明':json.loads(e['payload']).get('reason') or json.loads(e['payload']).get('note','')} for e in events]),hide_index=True,width='stretch')
    else:st.caption('此為舊紀錄，尚無升級後事件；不拿歷史欄位冒充當時已記錄的時間軸。')
    ref=db.execute('SELECT status,reason,observed_at FROM strategy_reference WHERE trade_id=?',(t['id'],)).fetchone()
    if ref:st.caption('最近參考狀態 '+ref[0]+' · '+ref[1]+' · '+ref[2]+' UTC；紙上成交狀態以交易紀錄為準。')
    if t['status']=='closed':
        result=t.get('post_trade_review') or review(t)
        st.write('**觀察標籤**：'+('、'.join(LABELS[k] for k in result['tags']) or '沒有符合固定觀察標籤'))
        if result['bridge']:st.dataframe(pd.DataFrame([result['bridge']]),hide_index=True,width='stretch')
        else:st.info('成本欄位不足，不能完整拆分原始價格、滑價與費用。')
        st.caption(result['note']);st.json(result,expanded=False)
    st.download_button('匯出生命週期與復盤',json.dumps({'trade_id':t['id'],'events':[dict(e) for e in events],'review':t.get('post_trade_review') or review(t)},ensure_ascii=False,indent=2),file_name=t['id']+'-lifecycle-review.json',mime='application/json')

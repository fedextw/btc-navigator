"""Observable training lifecycle, common-opportunity competition and local signal charts."""
import json
import altair as alt
import pandas as pd
import streamlit as st
from strategy_growth import compare
from strategy_learning import load
from terminal_ui import section,esc


def growth_center(db, profile, mode, rows):
    learner = load(db, profile, mode)
    closed = sum(r['status'] == 'closed' for r in rows)
    incumbent, challenger = learner.get('incumbent'), learner.get('challenger')
    worker = __import__('strategy_journal').state(db, 'worker')
    training = learner.get('last_training', {})
    section('AI成長中心', 'LEARNING / EVIDENCE / EVOLUTION')
    phases = [('01', '監控市場', worker.get('status', '等待背景程序')),
              ('02', '累積經驗', f'{closed} 筆結算 / 首次訓練至少200筆'),
              ('03', '訓練候選', '已有現行模型' if incumbent else '等待合格資料'),
              ('04', '未來競賽', '挑戰模型平行觀察中' if challenger else '等待新候選'),
              ('05', '證據升級', '按共同機會獲利與回撤比較')]
    st.markdown('<div class="growth-flow">'+''.join(f'<div class="growth-step"><b>{n}</b><strong>{esc(title)}</strong><small>{esc(note)}</small></div>' for n,title,note in phases)+'</div>',unsafe_allow_html=True)
    a,b,c = st.columns(3)
    a.metric('下一次樣本進度', f'{min(closed,200)} / 200' if not incumbent else f'{max(0,closed-learner.get("last_source_count",closed))} / 20 新結算')
    b.metric('已封存策略模型', db.execute('SELECT COUNT(*) FROM strategy_models WHERE profile=? AND mode=?',(profile,mode)).fetchone()[0])
    c.metric('已記錄升級次數', sum(h.get('decision')=='晉升影子模型' for h in learner.get('history',[])))
    st.progress(min(1.,closed/200) if not incumbent else min(1.,max(0,closed-learner.get('last_source_count',closed))/20))
    def local(value):
        return pd.Timestamp(value).tz_convert('Asia/Taipei').strftime('%Y-%m-%d %H:%M:%S') if value else '尚無紀錄'
    st.caption('最近學習檢查（台北） '+local(learner.get('updated_at'))+' ｜ 最近訓練嘗試 '+local(learner.get('last_attempt')))
    st.info(training.get('result') or ('樣本不足，持續保存結構化分析與模擬紀錄；尚未訓練新策略模型。' if not incumbent else '現行模型持續保存事前預測，等待足夠新樣本再訓練。'))
    st.caption('至少200筆合格結算嘗試首次訓練；之後至少24小時及20筆新結算，且無待比較候選。資料切分或驗證淨R不合格會保留現況。Ollama是文字解讀，不是自動重訓語言模型。')
    attempts=db.execute('SELECT attempted_at,source_count,result,model_id FROM strategy_training_runs WHERE profile=? AND mode=? ORDER BY id DESC LIMIT 30',(profile,mode)).fetchall()
    with st.expander('查看真實訓練嘗試紀錄'):
        if attempts:st.dataframe(pd.DataFrame([{'嘗試時間UTC':r[0],'來源結算筆數':r[1],'結果':r[2],'模型版本':r[3]} for r in attempts]),hide_index=True,width='stretch')
        else:st.caption('尚無新版訓練嘗試紀錄；舊模型封存與晉升紀錄仍保留。')
    section('基準版本競賽', 'SAME OPPORTUNITIES · SAME RISK UNIT')
    if incumbent and challenger:
        report=compare(rows,incumbent['id'],challenger['id'],mode,sum(r['status']=='unresolved' for r in rows))
    else:
        report=learner.get('competition')
        if report:st.caption('最近一次競賽快照 · '+report.get('as_of','舊版未保存時間')+'；目前沒有平行候選。')
    if report:
        st.dataframe(pd.DataFrame([{'模型':name,'選擇筆數':record['selected'],'共同機會':record['opportunities'],'累計淨R':record['total_r'],'每機會平均R':record['mean_r_per_opportunity'],'最大回撤R':record['max_drawdown_r'],'參考勝率%':record['win_rate'],'版本':record['model_id']} for name,record in report['models'].items()]),hide_index=True,width='stretch')
        if report['curve']:
            frame=pd.DataFrame(report['curve']).melt('時間',var_name='模型',value_name='累計淨R')
            st.altair_chart(alt.Chart(frame).mark_line().encode(x=alt.X('時間:T',title='結算時間 UTC'),y='累計淨R:Q',color='模型:N',tooltip=['時間:T','模型:N','累計淨R:Q']).interactive(),width='stretch')
        interval=report['delta95_r']
        st.caption(f'共同結算機會 {report["common"]} 筆 / {report["days"]} 日 · 新減舊平均淨R區間：'+(f'{interval[0]:+.4f} ～ {interval[1]:+.4f}' if interval[0] is not None else '資料不足'))
        st.dataframe(pd.DataFrame([{'晉升比較條件':k,'通過':v} for k,v in report['checks'].items()]),hide_index=True,width='stretch')
        st.caption(report['note']+' 候選本身也必須通過獲利與風險門檻；不是僅靠勝率升級。')
        st.download_button('匯出模型競賽證據',json.dumps(report,ensure_ascii=False,indent=2),file_name=profile+'-competition.json',mime='application/json')
    else:st.info('尚無基準版本對照；多模型競賽請看下方AI強化實驗室。')
    if learner.get('history'):
        st.dataframe(pd.DataFrame([{k:h.get(k) for k in ('at','decision','old','candidate','reason')} for h in learner['history']]),hide_index=True,width='stretch')


def risk_panel(db,profile,mode,stats):
    from strategy_risk_ui import live_risk_panel
    live_risk_panel(stats,mode)
    section('獲利與風險成長面板','REALIZED CAPITAL / COSTS / DRAWDOWN')
    rows=stats['rows'];closed=[r for r in rows if r['status']=='closed'];a=stats['account']
    one,two,three,four=st.columns(4)
    one.metric('策略已實現淨損益',f'{a["equity"]-a["initial"]:+,.2f} USDT' if a else '尚未建立')
    two.metric('每筆平均淨R',f'{stats["average_r"]:+.3f}R' if stats['average_r'] is not None else '尚無樣本')
    three.metric('已結算手續費',f'{sum(r.get("fees",0) for r in closed):,.2f} USDT')
    four.metric('已結算資金費支出',f'{sum(r.get("funding",0) for r in closed):+,.2f} USDT')
    reserved=sum(r.get('reserved',0) for r in rows if r['status'] in ('pending','open','unresolved'))
    st.caption(f'預留／占用本金 {reserved:,.2f} USDT · 可用未預留資金 {max(0,a["equity"]-reserved):,.2f} USDT' if a else '兩個策略的帳戶獨立，不相加報酬。')
    st.caption('帳戶包含所有原始策略候選，不是AI篩選子集。已實現權益含進場費用，不含持倉浮動損益；回撤可能低估盤中風險。滑價已反映成交價，資金費來源以逐筆紀錄為準，負值為收入。')
    events=db.execute('SELECT observed_at,equity FROM strategy_equity WHERE strategy=? AND mode=? ORDER BY id',(profile,mode)).fetchall()
    if a:
        points=[{'時間':a['created_at'],'權益USDT':a['initial']}]+[{'時間':r[0],'權益USDT':r[1]} for r in events]
        f=pd.DataFrame(points);f['時間']=pd.to_datetime(f['時間'],utc=True)
        f['回撤%']=(1-f['權益USDT']/f['權益USDT'].cummax())*100
        if len(f)>2000:
            f=f.tail(2000)
            st.caption('權益圖顯示最近2000次觀察；回撤先以完整紀錄高點計算，帳戶累計數字仍涵蓋全部歷史。')
        view=st.radio('風險圖表',['已實現權益','已實現回撤'],horizontal=True,key='risk-view-'+profile)
        y='權益USDT' if view=='已實現權益' else '回撤%'
        st.altair_chart(alt.Chart(f).mark_area(opacity=.3,line=True,color='#57edc3' if y=='權益USDT' else '#ff8ba9').encode(x=alt.X('時間:T',title='觀察時間 UTC'),y=alt.Y(y+':Q',scale=alt.Scale(zero=False)),tooltip=['時間:T','權益USDT:Q','回撤%:Q']).interactive(),width='stretch')
    if closed:
        f=pd.DataFrame([{'日期':pd.Timestamp(r.get('settled_at',r['exit_time'])).tz_convert('Asia/Taipei').strftime('%Y-%m-%d'),'淨損益':r['pnl']} for r in closed]).groupby('日期',as_index=False).sum()
        st.altair_chart(alt.Chart(f).mark_bar().encode(x='日期:O',y='淨損益:Q',color=alt.condition(alt.datum['淨損益']>=0,alt.value('#57edc3'),alt.value('#ff8ba9')),tooltip=['日期','淨損益:Q']),width='stretch')
        st.caption('台北結算確認日損益；不回填成更早的已知獲利。此圖不包含未結算交易的進場費，與帳戶權益可能暫時不同。')


def signal_chart(candles,trade,show_levels=True):
    f=candles.copy()
    f['time']=pd.to_datetime(f['time'],utc=True)
    color=alt.condition('datum.close >= datum.open',alt.value('#57edc3'),alt.value('#ff8ba9'))
    brush=alt.selection_interval(encodings=['x'],name='signal_window')
    base=alt.Chart(f).encode(x=alt.X('time:T',title='K線開盤 UTC',scale=alt.Scale(domain=brush)))
    wick=base.mark_rule().encode(y=alt.Y('low:Q',scale=alt.Scale(zero=False),title='USDT'),y2='high:Q',color=color,tooltip=['time:T','open:Q','high:Q','low:Q','close:Q'])
    body=base.mark_bar(size=5).encode(y='open:Q',y2='close:Q',color=color)
    layers=[wick,body]
    if show_levels:
        levels=pd.DataFrame([{'價位':trade.get('entry',trade['reference']),'類型':'模擬成交' if trade.get('entry') else '參考進場'},
                             {'價位':trade['target'],'類型':'止盈'},{'價位':trade['stop'],'類型':'止損'}])
        layers.append(alt.Chart(levels).mark_rule(strokeDash=[6,4]).encode(y='價位:Q',color=alt.Color('類型:N',scale=alt.Scale(domain=['參考進場','模擬成交','止盈','止損'],range=['#b9a5ff','#b9a5ff','#57edc3','#ff8ba9'])),tooltip=['類型:N','價位:Q']))
    events=[{'時間':trade['signal_time'],'事件':'訊號保存依據K線'}]
    for key,label in [('entry_time','模擬進場'),('exit_time','模擬出場')]:
        if trade.get(key):events.append({'時間':trade[key],'事件':label})
    visible=[e for e in events if f.time.min()<=pd.Timestamp(e['時間'])<=f.time.max()]
    if visible:
        layers.append(alt.Chart(pd.DataFrame(visible)).mark_rule(color='#ccd6ee',opacity=.55,strokeDash=[2,3]).encode(x='時間:T',tooltip=['時間:T','事件:N']))
    overview=alt.Chart(f).mark_area(opacity=.25,color='#8d9dff').encode(x=alt.X('time:T',title='拖曳下方時間範圍 · 雙擊還原'),y=alt.Y('close:Q',scale=alt.Scale(zero=False),title=None)).properties(height=65).add_params(brush)
    return alt.vconcat(alt.layer(*layers).properties(height=340),overview).resolve_scale(color='independent')


def interactive_signal_panel(rows,root,mode):
    section('互動訊號圖表','CANDLESTICKS / ENTRY / TP / SL')
    if not rows:
        st.info('尚無策略交易。累積候選後，可選擇交易並直接在K線上核對進場與風險。');return
    ordered=sorted(rows,key=lambda r:r['created_at'],reverse=True)
    identity=st.selectbox('圖表交易', [r['id'] for r in ordered],format_func=lambda key:next(f'{r["symbol"]} · {r["side"]} · {r["status"]} · {r["created_at"]}' for r in ordered if r['id']==key))
    trade=next(r for r in ordered if r['id']==identity)
    from signal_store import connect
    db=connect(root)
    try:record=db.execute('SELECT payload FROM scan_cache WHERE symbol=? AND interval=? AND mode=?',(trade['symbol'],trade['interval'],mode)).fetchone()
    finally:db.close()
    if not record:
        st.info('沒有這筆交易的本機K線快取；等待背景補齊，不以其他價格資料替代。');return
    f=pd.DataFrame(json.loads(record[0]));f['time']=pd.to_datetime(f['time'],utc=True);f['close_time']=pd.to_datetime(f['close_time'],utc=True)
    f=f[f.close_time<=pd.Timestamp.now(tz='UTC')].sort_values('time')
    if f.empty:st.info('尚無已收盤K線。');return
    count=st.slider('訊號圖顯示根數',50,300,150,25)
    levels=st.checkbox('顯示進場／止盈／止損線',True)
    st.altair_chart(signal_chart(f.tail(count),trade,levels),width='stretch')
    st.caption(f'{trade["symbol"]} / {trade["interval"]} / {mode} · 快取最後收盤 {f.iloc[-1].close_time} · 圖上價位來自當時保存的策略紀錄；滑動下方總覽可選區間。')
    if pd.Timestamp(trade['signal_time'])<f.iloc[0].time:st.warning('此交易早於目前快取範圍；圖中只有近期行情，不能當作完整成交路徑。')
    st.dataframe(pd.DataFrame([{'判斷條件':k,'通過':v} for k,v in trade.get('checks',{}).items()]),hide_index=True,width='stretch')

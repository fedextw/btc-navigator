"""Interactive research desk: linked brush, candles, regimes and decision evidence."""
import json
from pathlib import Path
import altair as alt
import pandas as pd
import streamlit as st

from analysis_engine import analyze
from decision_research import explain
from learning_lab import load_record, model_path, save_record
from market_data import SYMBOLS, valid_symbol
from market_regime import regime_frame, LABELS
from multi_timeframe import compare
from research_data import load_bundle, history
from runtime_config import STATE_ROOT
from signal_store import connect, get_state
from terminal_ui import hero, section, esc

COLORS={'trend_up':'#54efc3','trend_down':'#ff8ba9','range':'#a899ff','high_volatility':'#f7c76b','mixed':'#7188aa','insufficient':'#374258'}


@st.cache_data(ttl=60,show_spinner=False)
def bundle(symbol,mode):
    return load_bundle(symbol,mode)


def brush_bounds(selection):
    values=selection.get('focus',{}).get('time') if isinstance(selection,dict) else None
    if not isinstance(values,list) or len(values)!=2:
        return None
    try:
        bounds=[pd.to_datetime(v,unit='ms',utc=True) if isinstance(v,(int,float)) else pd.Timestamp(v) for v in values]
        if any(pd.isna(v) or v.tzinfo is None for v in bounds) or bounds[0]>=bounds[1]:
            return None
        return bounds
    except (TypeError,ValueError,OverflowError):
        return None


def interactive_chart(frame,result,scope):
    section('價格與行情地圖','BRUSH · ZOOM · INSPECT')
    a,b,c=st.columns([2,1,1])
    window=a.slider('顯示最近 K 線根數',60,min(300,len(frame)),min(180,len(frame)),step=10,key='chart_window_'+scope)
    ema=b.checkbox('顯示 EMA',True,key='chart_ema_'+scope)
    levels=c.checkbox('顯示研究價位',True,key='chart_levels_'+scope)
    full=frame.tail(window).copy()
    full['行情']=full.regime.map(LABELS)
    palette=alt.Scale(domain=list(LABELS.values()),range=[COLORS[k] for k in LABELS])
    focus=alt.selection_interval(name='focus',encodings=['x'],clear='dblclick')
    preview=alt.Chart(full).mark_area(color='#7188aa',opacity=.3,line={'color':'#a899ff','strokeWidth':1}).encode(
        x=alt.X('time:T',title='拖曳選取時段；雙擊縮圖清除選取（UTC）',axis=alt.Axis(format='%m/%d %H:%M')),
        y=alt.Y('close:Q',title=None,scale=alt.Scale(zero=False),axis=None),
        opacity=alt.condition(focus,alt.value(.6),alt.value(.2))).add_params(focus).properties(height=130)
    event=st.altair_chart(preview.configure_view(stroke=None),key='focus_'+scope+'/'+str(window),width='stretch',on_select='rerun',selection_mode=['focus'])
    selection=dict(event.selection) if hasattr(event,'selection') else {}
    bounds=brush_bounds(selection)
    visible=full[(full.time>=bounds[0])&(full.time<=bounds[1])] if bounds else full
    if len(visible)<2:
        st.info('選取範圍不足兩根 K 線，請擴大範圍。')
        return
    base=alt.Chart(visible).encode(x=alt.X('time:T',title=None,axis=alt.Axis(format='%m/%d %H:%M')))
    colors=alt.condition('datum.close >= datum.open',alt.value('#54efc3'),alt.value('#ff8ba9'))
    tooltip=[alt.Tooltip('time:T',title='開盤時間 UTC'),alt.Tooltip('open:Q',title='開盤'),alt.Tooltip('high:Q',title='最高'),alt.Tooltip('low:Q',title='最低'),alt.Tooltip('close:Q',title='收盤'),alt.Tooltip('volume:Q',title='成交量'),'行情:N']
    layers=[base.mark_rule().encode(y=alt.Y('low:Q',title='USDT',scale=alt.Scale(zero=False)),y2='high:Q',color=colors),
        base.mark_bar(size=5).encode(y='open:Q',y2='close:Q',color=colors,tooltip=tooltip)]
    if ema:
        for field,color in [('ema20','#f7c76b'),('ema50','#7d9cff'),('ema200','#a899ff')]:
            layers.append(base.mark_line(color=color,strokeWidth=1.3).encode(y=f'{field}:Q'))
    if levels and result['side']!='WAIT' and result.get('stop'):
        prices=pd.DataFrame([{'價格':result['entry'],'價位':'參考收盤'}, {'價格':result['stop'],'價位':'ATR 假設停損'},
            {'價格':result['targets'][1],'價位':'ATR 假設 2R 目標'}])
        layers.append(alt.Chart(prices).mark_rule(strokeDash=[5,4],opacity=.7).encode(y='價格:Q',color=alt.Color('價位:N',scale=alt.Scale(range=['#ff8ba9','#54efc3','#a899ff']),legend=alt.Legend(orient='bottom')),tooltip=['價位:N','價格:Q']))
    hover=alt.selection_point(name='cursor',nearest=True,on='pointerover',fields=['time'],empty=False,clear='pointerout')
    layers.append(base.mark_circle(opacity=0,size=90).encode(y='close:Q').add_params(hover))
    layers.append(base.mark_rule(color='#d8e1f1',opacity=.45).encode(tooltip=tooltip).transform_filter(hover))
    chart=alt.layer(*layers).properties(height=360).interactive(bind_y=False).configure_view(stroke=None)
    st.altair_chart(chart,key='candles_'+scope,width='stretch')
    regimes=alt.Chart(visible).mark_tick(thickness=9,size=24).encode(x=alt.X('time:T',title=None,axis=None),color=alt.Color('行情:N',scale=palette,legend=alt.Legend(orient='bottom')),tooltip=['time:T','行情:N','adx:Q','atr_pct:Q']).properties(height=95)
    st.altair_chart(regimes.configure_view(stroke=None),width='stretch')
    volume=base.mark_bar(opacity=.7).encode(y=alt.Y('volume:Q',title='成交量'),color=colors,tooltip=tooltip).properties(height=100)
    st.altair_chart(volume.configure_view(stroke=None),width='stretch')
    st.caption(f'已選取 {len(visible)} 根 · 滾輪縮放主圖、拖曳平移、滑鼠檢視 OHLC；時間選取只改變圖表，不回寫訊號。價位來自基準規則，非實際委託。')


def timeframe_chart(multi):
    section('多週期共識矩陣','POINT-IN-TIME / SHADOW')
    rows=[]
    for r in multi['rows']:
        for name,side in [('趨勢',r['trend']),('規則',r['rule_side'])]:
            rows.append({'週期':r['interval'],'觀察':name,'方向':side if r['valid'] else '無效',
                '角色':r['role'],'行情':r['regime'],'收盤UTC':r['candle_time'] or '—','原因':r['reason']})
    chart=alt.Chart(pd.DataFrame(rows)).mark_rect(cornerRadius=6,stroke='#162033',strokeWidth=4).encode(
        x=alt.X('觀察:N',title=None,axis=alt.Axis(orient='top',labelAngle=0)),
        y=alt.Y('週期:N',sort=['4h','1h','15m'],title=None),
        color=alt.Color('方向:N',scale=alt.Scale(domain=['LONG','SHORT','WAIT','無效'],range=['#2c947d','#b84f6d','#4d527d','#263248']),legend=alt.Legend(orient='bottom')),
        tooltip=['週期:N','角色:N','觀察:N','方向:N','行情:N','收盤UTC:N','原因:N']).properties(height=190)
    st.altair_chart(chart.configure_view(stroke=None),width='stretch')
    st.write('**'+multi['status']+'** · 影子研究方向 '+multi['side'])
    st.caption(multi['note'])
    with st.expander('查看各週期資料時間與完整性'):
        st.dataframe(pd.DataFrame(multi['rows']),hide_index=True,width='stretch')


def walk_view(report):
    if not report:
        st.info('此模型尚無滾動驗證。新版自動訓練會保存報告，或按下方按鈕立即建立研究副本。')
        return
    section('三段滾動驗證','EXPANDING WINDOW / OUT OF SAMPLE')
    a,b,c,d=st.columns(4)
    a.metric('未見測試交易',report['baseline']['trades'])
    b.metric('未見測試淨報酬',f'{report["baseline"]["net_pct"]:+.2f}%')
    c.metric('測試最大回撤',f'{report["baseline"]["max_drawdown_pct"]:.2f}%')
    d.metric('正報酬分段',f'{sum(f["baseline"]["net_pct"]>0 for f in report["folds"])} / 3')
    timeline=[]; comparisons=[]
    for f in report['folds']:
        for label,start,end in [('訓練',f['train_first'],f['train_last_outcome']),('驗證',f['validation_first'],f['validation_last_outcome']),('測試',f['test_first'],f['test_last_outcome'])]:
            timeline.append({'分段':f'Fold {f["fold"]}','階段':label,'開始':start,'結束':end})
        for key,label in [('baseline','基準模型'),('regime_filter','順勢行情篩選')]:
            stats=f[key];comparisons.append({'分段':f'Fold {f["fold"]}','方法':label,'淨報酬%':stats['net_pct'],'交易數':stats['trades'],'最大回撤%':stats['max_drawdown_pct']})
    st.altair_chart(alt.Chart(pd.DataFrame(timeline)).mark_bar(cornerRadius=3,size=17).encode(
        x=alt.X('開始:T',title='時間 UTC'),x2='結束:T',y=alt.Y('分段:N',title=None),
        color=alt.Color('階段:N',scale=alt.Scale(domain=['訓練','驗證','測試'],range=['#435a80','#a899ff','#54efc3'])),
        tooltip=['分段:N','階段:N','開始:T','結束:T']).properties(height=140).configure_view(stroke=None),width='stretch')
    st.altair_chart(alt.Chart(pd.DataFrame(comparisons)).mark_bar(cornerRadiusTopLeft=3,cornerRadiusTopRight=3).encode(
        x=alt.X('分段:N',title=None,axis=alt.Axis(labelAngle=0)),xOffset='方法:N',y='淨報酬%:Q',
        color=alt.Color('方法:N',scale=alt.Scale(range=['#a899ff','#54efc3'])),tooltip=['分段:N','方法:N','淨報酬%:Q','交易數:Q','最大回撤%:Q']).properties(height=210).configure_view(stroke=None),width='stretch')
    st.caption('順勢篩選採固定規則，只保留上升趨勢多單／下降趨勢空單，不根據測試結果調參。報酬較高但樣本很少，仍不能判定較好。')
    st.dataframe(pd.DataFrame([{'檢驗':k,'結果':'通過' if v else '未通過'} for k,v in report['checks'].items()]),hide_index=True,width='stretch')
    with st.expander('檢查資料邊界、模型參數與限制'):
        st.json([{k:v for k,v in f.items() if k not in ('model','baseline','regime_filter')} for f in report['folds']])
        for line in report['limitations']:st.caption('• '+line)
    st.download_button('下載滾動驗證完整報告',json.dumps(report,ensure_ascii=False,indent=2),file_name='walk-forward.json',mime='application/json')


def decision_desk(symbols):
    hero('RESEARCH / INTERACTIVE DECISION DESK','讓訊號的每個條件，都看得見。','拖曳時間、切換週期、對照市場環境與未見資料驗證。研究證據與正式背景訊號分開呈現。',[('互動研究','green'),('不修改正式門檻','')])
    st.session_state.setdefault('research_symbol',st.session_state.get('selected_symbol','BTCUSDT'))
    a,b,c,d=st.columns([2,1,1,1])
    symbol=a.selectbox('研究交易對',sorted(set(symbols)|{st.session_state['research_symbol']}),key='research_symbol',accept_new_options=True).strip().upper()
    pending_interval=st.session_state.pop('pending_research_interval',None)
    pending_mode=st.session_state.pop('pending_research_mode',None)
    if pending_interval in ('1h','15m','4h'):st.session_state['research_interval']=pending_interval
    if pending_mode in ('live','demo'):st.session_state['research_mode']=pending_mode
    st.session_state.setdefault('research_interval','1h')
    st.session_state.setdefault('research_mode','demo' if __import__('os').environ.get('BTC_NAVIGATOR_DEMO')=='1' else 'live')
    interval=b.selectbox('決策基準週期',['1h','15m','4h'],key='research_interval',index=None)
    mode=c.selectbox('決策台資料來源',['live','demo'],key='research_mode',index=None,format_func=lambda x:'真實行情' if x=='live' else '示範資料')
    if d.button('重新讀取行情',width='stretch'):
        bundle.clear()
    if not valid_symbol(symbol):
        st.error('請填 Binance USDT 合約代號，例如 ETHUSDT。');return
    with st.spinner('對齊三個週期的已收盤行情…'):
        markets,errors=bundle(symbol,mode)
    for period,error in errors.items():st.warning(period+'：'+error)
    if interval not in markets:
        st.error('基準週期行情不可用，停止本次判斷；不切換成示範行情。');return
    market=markets[interval]
    if mode=='demo':st.warning('目前為合成示範資料；圖表、驗證與方向均不是目前真實行情。')
    result=analyze(market)
    as_of=market['candles'].iloc[-1].close_time
    multi=compare(markets,as_of,mode)
    record=load_record(model_path(STATE_ROOT/'models',symbol,interval,mode=='demo'))
    key=f'walk/{symbol}/{interval}/{mode}'
    manual_path=model_path(STATE_ROOT/'walk-research',symbol,interval,mode=='demo')
    manual=load_record(manual_path)
    automatic=(record or {}).get('walk_forward')
    sources=(["現行模型附帶"] if automatic else []) + (["手動研究副本"] if manual else [])
    report=None
    select_key='walk_source/'+key
    pending=st.session_state.pop('walk_source_pending/'+key,None)
    options=sources or ['尚無報告']
    if pending in options:
        st.session_state[select_key]=pending
    if st.session_state.get(select_key) not in options:
        st.session_state[select_key]=options[0]
    source=st.selectbox('滾動報告來源',options,key=select_key,index=None,disabled=not sources)
    if sources:
        report=automatic if source=='現行模型附帶' else manual
        st.caption('報告 '+report['id']+' · '+report['created_at']+' · 手動副本不會取代交易模型。')
    else:
        st.caption('尚無報告，可在滾動驗證頁籤建立研究副本；不取代現行交易模型。')
    db=connect()
    try:
        row=db.execute('SELECT payload FROM scan_results WHERE symbol=? AND interval=? AND mode=?',(symbol,interval,mode)).fetchone()
        snapshot=json.loads(row[0]) if row else None
    finally:db.close()
    decision=explain(market,result,snapshot,report,multi)
    a,b,c,d=st.columns(4)
    a.metric('背景原訊號',decision['formal_side'])
    b.metric('目前市場環境',decision['regime']['label'])
    c.metric('多週期研究',multi['status'])
    d.metric('滾動研究檢驗','通過（影子）' if report and report['evidence_pass'] else '待驗證／未通過')
    st.caption('基準收盤 UTC：'+str(as_of)+' · 本頁行情不包含當前資金費／OI，規則可與背景掃描器不同；正式方向只採同根、近期背景快照。')
    tabs=st.tabs(['互動行情','訊號決策面板','滾動驗證'])
    with tabs[0]:
        left,right=st.columns([2.3,1])
        with left:interactive_chart(regime_frame(market['candles']),result,f'{symbol}/{interval}/{mode}')
        with right:
            timeframe_chart(multi)
            st.caption('行情分類：ADX 衡量趨勢強度；ATR% 描述相對波動；這些數值不是勝率。')
            st.json({k:decision['regime'].get(k) for k in ('adx','atr_pct','efficiency')},expanded=False)
    with tabs[1]:
        section('原訊號門檻與影子條件','EXPLAIN / CHALLENGE / INVALIDATE')
        gates=[{'類型':'原背景門檻','條件':k,'結果':'通過' if v else '未通過'} for k,v in decision['formal_gates'].items()]
        gates += [{'類型':'影子研究','條件':k,'結果':'通過' if v else '未通過'} for k,v in decision['shadow_gates'].items()]
        data=pd.DataFrame(gates)
        gatechart=alt.Chart(data).mark_rect(cornerRadius=4,stroke="#142033",strokeWidth=3).encode(x=alt.X('結果:N',title=None),y=alt.Y('條件:N',title=None,sort=None),color=alt.Color('類型:N',scale=alt.Scale(range=['#a899ff','#54efc3'])),tooltip=['類型:N','條件:N','結果:N']).properties(height=max(220,len(gates)*24))
        st.altair_chart(gatechart.configure_view(stroke=None),width='stretch')
        a,b=st.columns(2)
        with a:
            st.markdown('**為什麼觀望／什麼情況失效？**')
            for line in decision['blockers']+decision['invalidation']:st.write('• '+line)
        with b:
            st.markdown('**反證與資料限制**')
            for line in decision['contrary'] or ['目前沒有額外反證，不代表風險消失']:st.write('• '+line)
        similar=decision['regime_history']
        if similar and similar['trades']>=20:
            st.info(f'同類行情在滾動未見測試中有 {similar["trades"]} 筆；平均淨報酬 {similar["expectancy_pct"]:+.3f}%，勝率 {similar["win_rate"]:.1f}%。這不是本次訊號的勝率。')
        else:st.info('同類行情尚無至少 20 筆未見交易，暫不顯示類似訊號勝率。')
        st.download_button('下載本次決策證據',json.dumps({'symbol':symbol,'interval':interval,'mode':mode,'as_of':str(as_of),'decision':decision,'multi_timeframe':multi,'walk_id':(report or {}).get('id')},ensure_ascii=False,indent=2),file_name='decision-evidence.json',mime='application/json')
    with tabs[2]:
        with st.form('walk-research'):
            st.caption('手動建立研究副本，不替換現行模型。自動訓練的新模型也會附帶此報告。')
            a,b,c=st.columns(3)
            horizon=a.selectbox('滾動研究持有根數',[3,6,12],index=1)
            fee=b.number_input('滾動研究單邊費率（%）',0.0,1.0,.05,.01)
            slip=c.number_input('滾動研究單邊滑價（%）',0.0,1.0,.02,.01)
            submitted=st.form_submit_button('執行三段滾動驗證',type='primary')
        if submitted:
            try:
                from walk_forward import evaluate
                with st.spinner('取得最多 1,500 根歷史，依序訓練、驗證與未見測試…'):
                    candles=history(symbol,interval,mode)
                    candles=candles[candles.close_time<=as_of].copy()
                    report_copy=evaluate(candles,symbol,interval,mode=='demo',horizon,fee,slip)
                    report_copy['origin']='manual_research'
                    save_record(manual_path,report_copy)
                    st.session_state['walk_source_pending/'+key]='手動研究副本'
                st.rerun()
            except Exception as exc:
                from binance_client import BinanceAccessError,RatePause
                st.error(str(exc) if isinstance(exc,(ValueError,BinanceAccessError,RatePause)) else '滾動驗證暫不可用；既有模型與報告保留。')
        walk_view(report)

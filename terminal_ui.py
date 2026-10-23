"""Mission control visuals, learning evidence, cost scenarios and health views."""
from datetime import datetime
import html
import json
import time
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from monitor_settings import load_settings
from runtime_config import STATE_ROOT
from signal_store import connect, get_state
from telemetry import training_activity, paper_totals, health_checks, journal_rows


def esc(value):
    return html.escape(str(value),quote=True)


def hero(kicker,title,description,pills=()):
    badges=''.join(f'<span class="pill {esc(color)}">{esc(text)}</span>' for text,color in pills)
    st.markdown(f'<div class="hero"><div class="kicker">{esc(kicker)}</div><h1>{esc(title)}</h1><p>{esc(description)}</p><div class="hero-footer">{badges}</div></div>',unsafe_allow_html=True)


def section(title,caption=''):
    st.markdown(f'<div class="section-head"><h3>{esc(title)}</h3><small>{esc(caption)}</small></div>',unsafe_allow_html=True)


def opportunities(rows):
    section('市場觀測焦點','MARKET RADAR / CLOSED CANDLES')
    leaders=sorted((r for r in rows if r.get('price') is not None),key=lambda r:(r['side']=='WAIT',-abs(r.get('score',0)),r['symbol']))[:3]
    if not leaders:
        st.info('等待第一輪行情。接上真實資料後，這裡會顯示實際掃描焦點。')
        return
    for col,row in zip(st.columns(3),leaders):
        side=row['side']; rule=row.get('rule_side','WAIT')
        color='long' if side=='LONG' else 'short' if side=='SHORT' else ''
        label=side if side!='WAIT' else '觀望 / 非訊號'
        reason='、'.join(row.get('reasons',[])[:2]) or '已通過目前研究條件，請核對時效與風險'
        col.markdown(f'<div class="op-card {color}"><div class="op-top"><span class="op-symbol">{esc(row["symbol"])}</span><span class="pill">{esc(label)}</span></div><div class="op-price">{row["price"]:,.5f}</div><div class="op-detail">規則 {esc(rule)} · 分數 {row.get("score",0):+d}<br>{esc(reason)}</div></div>',unsafe_allow_html=True)


@st.cache_data(ttl=30,show_spinner=False)
def activity(interval,mode):
    return training_activity(STATE_ROOT,interval,mode)


@st.cache_data(ttl=30,show_spinner=False)
def forward_rows(interval,mode):
    try:
        return journal_rows(STATE_ROOT,interval,mode=='demo')
    except (OSError, ValueError, KeyError):
        st.error('紙上紀錄無法完整讀取，請保留 .local-state/paper 檔案供檢查；不顯示不完整明細。')
        return []


def context(db):
    settings=load_settings()
    status=get_state(db,'status',{})
    interval=settings['interval']; mode=status.get('mode','live')
    active=set(get_state(db,'universe',{}).get('symbols',[]))
    summaries=[{'symbol':r['symbol'],**json.loads(r['payload'])} for r in db.execute('SELECT symbol,payload FROM paper_metrics WHERE interval=? AND mode=?',(interval,mode)) if mode=='demo' or not active or r['symbol'] in active]
    return settings,status,interval,mode,active,summaries


def paper_metrics(summaries):
    total=paper_totals(summaries)
    a,b,c,d=st.columns(4)
    a.metric('已結算紙上交易',f'{total["trades"]:,}')
    b.metric('紙上交易勝率',f'{total["win_rate"]:.1f}%' if total['win_rate'] is not None else '尚無樣本')
    c.metric('等待未來行情／無法還原',f'{total["pending"]} / {total["unresolved"]}')
    d.metric('平均每筆淨報酬 · 1× 名目',f'{total["average_pct"]:+.3f}%' if total['average_pct'] is not None else '尚無樣本')
    st.caption('跨幣種逐筆統計，不是投資組合報酬。紙上紀錄與合格推播訊號採不同門檻。')
    return total


@st.fragment(run_every=30)
def learning_page():
    db=connect()
    try:
        settings,status,interval,mode,active,summaries=context(db)
        hero('INTELLIGENCE / MODEL OBSERVATORY','讓每一次學習，都留下證據。','追蹤訓練、候選評估與未來紙上結果；模型更新不等於績效必然改善。',[(interval.upper(),''),('示範資料' if mode=='demo' else '真實資料研究','amber' if mode=='demo' else 'green')])
        section('持續模擬與學習紀錄','FORWARD VALIDATION')
        total=paper_metrics(summaries)
        runs=activity(interval,mode)
        a,b,c,d=st.columns(4)
        a.metric('今日訓練完成',runs['today'])
        b.metric('今日候選通過研究檢驗',runs['today_passed'])
        c.metric('本輪訓練完成',status.get('trained',0))
        d.metric("紙上 Profit factor", f'{total["profit_factor"]:.2f}' if total["profit_factor"] is not None and total["costs_complete"] else "尚無足夠資料")
        st.caption('今日採台北時間；通過研究檢驗不代表已晉升，也不是未來交易勝率。')
        tabs=st.tabs(['學習軌跡','紙上交易明細','資金與成本情境'])
        with tabs[0]:
            if runs['days']:
                bars=alt.Chart(pd.DataFrame(runs['days'])).mark_bar(color='#a899ff',cornerRadiusTopLeft=4,cornerRadiusTopRight=4).encode(x=alt.X('日期:N',sort=None,axis=alt.Axis(labelAngle=0)),y=alt.Y('訓練完成:Q',axis=alt.Axis(tickMinStep=1)),tooltip=['日期:N','訓練完成:Q','研究門檻通過:Q']).properties(height=220).configure_view(stroke=None)
                st.altair_chart(bars,width='stretch')
            section('模型自我更新與晉升紀錄','VERSION CONTROL')
            audits=[json.loads(r[0]) for r in db.execute("SELECT payload FROM scan_state WHERE name LIKE 'evolution/%'")]
            if audits:
                st.dataframe(pd.DataFrame([{'交易對':a.get('symbol','—'),'更新時間':a.get('observed_at','舊版未記錄'),'決策':a['decision'],'原因':a['reason'],'現行模型':a.get('incumbent_id','首次'),'候選模型':a.get('candidate_id','—')} for a in audits]),hide_index=True,width='stretch')
            else:
                st.info('尚無自動更新紀錄。首次模型需要排隊，重訓需要足夠新 K 線與時間。')
            if runs['recent']:
                section('最近訓練紀錄','LATEST 60 RUNS')
                st.dataframe(pd.DataFrame(runs['recent']),hide_index=True,width='stretch')
            st.caption('保留現行模型可能表示候選未改善，屬正常決策。原模型過期時系統仍會停止訊號。')
        with tabs[1]:
            rows=forward_rows(interval,mode)
            available=sorted({r['symbol'] for r in rows})
            symbol=st.selectbox('篩選紙上交易幣種',['全部']+available)
            state=st.selectbox('篩選紙上交易狀態',['全部','pending','closed','unresolved'])
            selected=[r for r in rows if (symbol=='全部' or r['symbol']==symbol) and (state=='全部' or r['status']==state)]
            if selected:
                st.dataframe(pd.DataFrame(selected).sort_values('signal_time',ascending=False).head(200),hide_index=True,width='stretch')
                st.download_button('匯出篩選後紙上紀錄 · CSV',pd.DataFrame(selected).to_csv(index=False),file_name='paper-trades.csv',mime='text/csv')
            else:
                st.info('尚無符合條件的紀錄。等待新收盤 K 線與模型方向成立；不會補造交易。')
            st.caption('pending：等待進場或出場資料；closed：已結算；unresolved：資料無法還原。資料快取最多 30 秒。')
        with tabs[2]:
            cost_scenario(forward_rows(interval,mode), f"{interval}/{mode}")
    finally:
        db.close()


def cost_scenario(rows, scope):
    from portfolio_replay import replay
    section('資金與交易成本壓力測試','SCENARIO / NOT LIVE EXECUTION')
    st.caption('僅重播已結算的未來紙上紀錄，保留原固定持有期。加入共用資金、同時持倉限制、雙邊費用、價差與滑價。未結算／無法還原的紀錄排除，不可當成完整帳戶績效。')
    with st.form('cost-scenario'):
        a,b,c=st.columns(3)
        initial=a.number_input('模擬初始資金（USDT）',100.0,1e8,10000.0,100.0)
        allocation=b.number_input('每筆配置資金（%）',1.0,100.0,10.0,1.0)
        slots=c.number_input('最多同時持倉',1,20,5)
        a,b,c,d=st.columns(4)
        fee=a.number_input('情境單邊費率（%）',0.0,1.0,.05,.01)
        slip=b.number_input('情境單邊滑價（%）',0.0,1.0,.02,.01)
        spread=c.number_input('情境買賣價差（%）',0.0,1.0,.02,.01)
        funding=d.number_input('假設每 8h 資金費率（%）',-1.0,1.0,.01,.01)
        submitted=st.form_submit_button('計算資金與成本情境',type='primary')
    if submitted:
        report=replay(rows,initial,allocation,int(slots),fee,slip,spread,funding)
        st.session_state['cost_report/' + scope]=report
    report=st.session_state.get('cost_report/' + scope)
    if report:
        if not report["trades"]:
            st.info("尚無納入交易，結果只是初始資金，不能代表策略績效。")
        a,b,c,d=st.columns(4)
        a.metric('情境期末資金',f'{report["final"]:,.2f}')
        b.metric('情境淨報酬',f'{report["net_pct"]:+.2f}%')
        c.metric('已實現權益回撤',f'{report["realized_drawdown_pct"]:.2f}%')
        d.metric('納入／資金限制跳過',f'{len(report["trades"])} / {report["skipped"]}')
        st.caption(f'排除非結算或無效紀錄 {report["excluded"]} 筆。假設：{report["assumptions"]}')
        chart=pd.DataFrame(report['curve']);chart['結算順序']=range(len(chart))
        st.altair_chart(alt.Chart(chart).mark_line(color='#54efc3',point=True).encode(x='結算順序:Q',y=alt.Y('已實現權益:Q',scale=alt.Scale(zero=False)),tooltip=['時間:N','已實現權益:Q']).properties(height=230).configure_view(stroke=None),width='stretch')
        st.download_button('匯出成本情境 · JSON',json.dumps(report,ensure_ascii=False,indent=2),file_name='cost-scenario.json',mime='application/json')
    st.warning('資金費採你填寫的固定假設、按持有時間比例估算，正值為多付空收；不是歷史實際結算資料。採 1× 資金配置，未含未實現損益、槓桿強平、ATR 停損停利或真實撮合；回撤可能低估持倉期間風險。情境結果不改寫原紀錄或訓練門檻。')


@st.fragment(run_every=10)
def health_page():
    db=connect()
    try:
        settings,status,interval,mode,active,summaries=context(db)
        delivery=get_state(db,'delivery_status',{}); ai=get_state(db,'auto_ai_status',{})
        checks=health_checks(status,delivery,ai,settings)
        hero('OPERATIONS / SYSTEM HEALTH','掌握每一個運作環節。','掃描心跳、背景程序與資料錯誤集中顯示；程序在線與服務實際可用分開驗證。',[('僅本機存取','green'),('每 10 秒更新','')])
        for check in checks:
            color='green' if check['ok'] is True else 'amber' if check['ok'] is False else ''
            st.markdown(f'<div class="health-row"><div><div class="health-name">{esc(check["name"])}</div><div class="health-note">{esc(check["note"])}</div></div><span class="pill {color}">{esc(check["state"])}</span></div>',unsafe_allow_html=True)
        section('資料與投遞狀態','DIAGNOSTICS')
        a,b,c,d=st.columns(4)
        a.metric('本輪資料失敗',status.get('failed',0));b.metric('本輪延後',status.get('deferred',0))
        issues=db.execute("SELECT COUNT(*) FROM deliveries WHERE status IN ('unknown','failed')").fetchone()[0]
        c.metric('歷史待檢查投遞',issues)
        stamp=status.get('updated_at')
        d.metric('掃描心跳',f'{max(0,int(time.time()-stamp))} 秒前' if stamp else '尚未啟動')
        for error in status.get('errors',[]): st.error(error)
        section('連線檢查','EXPLICIT CHECK / NO PAID REQUEST')
        st.caption('Ollama 檢查只讀已安裝模型，不下載、不付費；Telegram 實際手機送達請到設定中心按測試通知。')
        if st.button('檢查本機 Ollama'):
            from ai_research import check_ollama
            try:
                check_ollama(settings['ollama_model']); st.success('Ollama 已連線，指定模型存在。實際推論仍請在新聞與 AI 產生摘要。')
            except (RuntimeError,ValueError) as exc: st.error(str(exc))
        st.info('復原順序：確認電腦未休眠 → START 視窗仍開著 → 查看行情錯誤 → 檢查 .local-state/scanner.log。HTTP 451 代表服務地區限制；不要用示範資料替代真實行情。')
        diagnostics={'generated_at':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),'mode':mode,
            'interval':interval,'scan_state':status.get('status'),'analyzed':status.get('analyzed',0),
            'failed':status.get('failed',0),'deferred':status.get('deferred',0),
            'heartbeat_at':status.get('updated_at'),'checks':checks}
        st.download_button('下載無金鑰診斷摘要',json.dumps(diagnostics,ensure_ascii=False,indent=2),file_name='health-report.json',mime='application/json')
    finally:
        db.close()

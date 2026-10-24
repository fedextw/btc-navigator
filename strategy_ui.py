"""Fast signal cards, independent strategy accounts and auditable learning evidence."""
import json
import os
import altair as alt
import pandas as pd
import streamlit as st

from terminal_ui import hero,section,esc
from strategy_rules import PROFILES
from strategy_journal import connect,state,summary
from strategy_learning import load,evidence,selected_forward
from monitor_settings import load_settings,save_settings
from runtime_config import STATE_ROOT
from signal_store import connect as signals_db
from strategy_growth_ui import growth_center,risk_panel,interactive_signal_panel


def price(x):
    if x is None:return '—'
    return f'{x:,.2f}' if x>=10 else f'{x:.8g}'


def settings_panel():
    s=load_settings()
    with st.expander('趨勢／當沖策略、風險與研究推播設定',expanded=False):
        with st.form('strategy-settings'):
            enabled=st.checkbox('啟用雙策略背景模擬與學習',s['strategy_enabled'])
            a,b,c=st.columns(3)
            initial=a.number_input('新策略帳戶初始模擬資金',100.,1e8,float(s['strategy_initial']),100.)
            risk=b.number_input('每筆目標風險（%）',.1,2.,float(s['strategy_risk_pct']),.1)
            positions=c.number_input('每策略最多持倉／預留數',1,10,int(s['strategy_max_positions']))
            a,b,c,d=st.columns(4)
            daily=a.number_input('當日已確認損失上限（%）',.5,10.,float(s['strategy_daily_loss_pct']),.5)
            fee=b.number_input('策略單邊費率假設（%）',0.,1.,float(s['strategy_fee_pct']),.01)
            slip=c.number_input('策略單邊滑價假設（%）',0.,1.,float(s['strategy_slippage_pct']),.01)
            funding=d.number_input('策略每8h資金費假設（%）',-1.,1.,float(s['strategy_funding_pct_8h']),.01)
            quote_costs=st.checkbox('新候選使用即時報價成本壓測（缺資料暫停新候選）',s['strategy_quote_costs'])
            st.caption('只套用新的真實資料候選；半價差＋設定滑價為雙邊成本壓測，非未來深度撮合。已存在交易保留原成本。')
            ai=st.checkbox('自動保存策略 AI 文字分析（需同時啟用全域自動 AI）',s['strategy_ai_enabled'])
            alerts=st.checkbox('啟用通過獲利與風險門檻的策略 Telegram 推播',s['strategy_notifications'])
            st.caption('AI 與原訊號共用每日額度；Ollama 不需 API Key。推播仍需全域 Telegram 已啟用。初始資金只影響尚未建立的帳戶，不重寫既有績效；成本與風險設定只套用新預測。')
            if st.form_submit_button('儲存雙策略設定',type='primary'):
                save_settings({'strategy_quote_costs':quote_costs,'strategy_enabled':enabled,'strategy_initial':initial,'strategy_risk_pct':risk,
                    'strategy_max_positions':int(positions),'strategy_daily_loss_pct':daily,'strategy_fee_pct':fee,
                    'strategy_slippage_pct':slip,'strategy_funding_pct_8h':funding,'strategy_ai_enabled':ai,'strategy_notifications':alerts})
                st.success('已保存，背景下一輪套用；既有交易保留原始條件。')


def signal_card(t,qualifies):
    profile=PROFILES[t['strategy']]
    label='通過獲利與風險研究門檻' if qualifies else '模擬研究候選 · 獲利證據尚待驗證'
    tone='long' if t['side']=='LONG' else 'short'
    side='做多 LONG' if t['side']=='LONG' else '做空 SHORT'
    expired=t['status']=='pending' and pd.Timestamp.now(tz='UTC')>=pd.Timestamp(t['eligible_entry_time'])
    status={'pending':'參考已過期，等待K線確認模擬成交' if expired else '等待預定紙上進場','open':'紙上持倉中','closed':'已結算'}.get(t['status'],t['status'])
    entry=t.get('entry',t['reference'])
    entry_label='模擬成交' if t['status']=='open' else '參考進場'
    st.markdown(f'''<div class="op-card {tone}"><div class="op-top"><span class="op-symbol">{esc(t['symbol'])} · {esc(profile['name'])}</span><span class="pill">{esc(side)}</span></div>
<div class="op-detail">{esc(label)}<br>{esc(status)} · {esc(profile['version'])}</div>
<div class="op-price">{esc(entry_label)} {esc(price(entry))}</div>
<div style="display:flex;gap:24px;flex-wrap:wrap;font-size:18px"><span class="up">止盈 {esc(price(t['target']))}</span><span class="down">止損 {esc(price(t['stop']))}</span></div>
<div class="op-detail" style="margin-top:12px">基準 {esc(t['interval'])} · 最長 {profile['max_bars']} 根 · {esc(t['signal_time'])} UTC<br>參考有效至／預定紙上進場 {esc(t['eligible_entry_time'])} UTC<br>價位僅為紙上研究；非實盤成交或獲利保證。</div></div>''',unsafe_allow_html=True)


def learning_panel(db,profile,mode,rows):
    learner=load(db,profile,mode);closed=[r for r in rows if r['status']=='closed']
    model=learner.get('incumbent')
    chosen=selected_forward(closed,model['id']) if model else []
    proof=evidence(chosen,mode,sum(r['status']=='unresolved' for r in rows))
    growth_center(db,profile,mode,rows)
    from ai_intelligence_ui import intelligence_panel
    intelligence_panel(db,profile,mode,rows)
    section('獲利與風險研究資格','FORWARD EVIDENCE / NO WIN-RATE TARGET')
    a,b,c,d=st.columns(4)
    mean=proof['stats']['expectancy_pct']
    a.metric('AI選擇後平均淨報酬',f'{mean:+.3f}%' if mean is not None else '尚無樣本')
    b.metric('AI選擇後未來觀察勝率',f'{proof["win_rate"]:.1f}%' if proof['win_rate'] is not None else '尚無樣本')
    c.metric('選擇樣本／不同交易日',f'{proof["samples"]} / {proof["trading_days"]}')
    d.metric('AI選擇後逐筆回撤',f'{proof["stats"]["max_drawdown_pct"]:.2f}%')
    st.info(proof['label'])
    interval=proof['expectancy95_pct']
    st.caption('近90天最多200筆已事前選擇的未來結算交易；以台北結算日群聚重抽樣。平均淨報酬95%近似區間：'+(f'{interval[0]:+.3f}% ～ {interval[1]:+.3f}%' if interval[0] is not None else '樣本不足')+'。此區間未涵蓋跨日相關及反覆檢驗偏誤；逐筆1×曲線不是組合帳戶ROI。')
    st.dataframe(pd.DataFrame([{'研究資格':k,'狀態':'通過' if v else '未通過'} for k,v in proof['checks'].items()]),hide_index=True,width='stretch')
    if model:
        st.write('**現行影子模型**：'+model['id']+' · '+model['trained_at'])
        st.caption(f'過去資料 {model["source_count"]} 筆；驗證集選門檻 {model["threshold"]:.0%}，不是宣稱達到此勝率。')
        with st.expander('查看模型資料切分與歷史保留測試'):
            st.json(model['split']);st.json(model['test_stats'])
    else:st.info(f'已結算 {len(closed)} 筆；至少200筆合格的未來紙上紀錄才嘗試訓練策略模型，資料邊界不足時繼續累積。')
    if learner.get('challenger'):
        st.write('**平行候選模型**：'+learner['challenger']['id'])
        st.caption('先保存兩版本預測，等待共同未來樣本；各至少100筆被選擇交易並通過保守條件才比較晉升。')

    st.caption('策略規則版本固定；AI學習候選在成本後獲利的條件，不以勝率為升級目標，也不自行改寫止盈止損。策略帳戶績效包含原始候選，AI選擇子集不等於另開的組合帳戶。')
    with st.expander('查看歷史策略模型版本'):
        versions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM strategy_models WHERE profile=? AND mode=? ORDER BY created_at DESC LIMIT 30',(profile,mode))]
        if versions:
            st.dataframe(pd.DataFrame([{'版本':v['id'],'訓練時間':v['trained_at'],'來源筆數':v['source_count'],'保留測試選擇數':v['test_selected'],'選擇門檻':v['threshold']} for v in versions]),hide_index=True,width='stretch')
            st.download_button('匯出策略模型版本與評估',json.dumps(versions,ensure_ascii=False,indent=2),file_name=profile+'-model-versions.json',mime='application/json')
        else:st.caption('樣本尚未足夠訓練，沒有虛構的模型版本。')
    review=db.execute('SELECT payload FROM strategy_reviews WHERE strategy=? AND mode=? ORDER BY observed_at DESC LIMIT 1',(profile,mode)).fetchone()
    section('規律探索與後段確認','EXPLORATORY / NOT AUTOMATIC ORDERS')
    if review:
        report=json.loads(review[0])
        table=[{'條件':r['feature'],'值':r['value'],'探索筆數':r['discovery']['trades'],'確認筆數':r['confirmation']['trades'],
            '確認平均淨報酬%':r['confirmation']['expectancy_pct'],'探索性支持':r['exploratory_support']} for r in report['patterns']]
        st.dataframe(pd.DataFrame(table),hide_index=True,width='stretch');st.caption(report['note'])
    else:st.info('至少60筆未來結算交易後，分早期探索／後期確認；固定檢查行情、時段、波動、方向與觸發型態，不自動把偶然規律變成下單策略。')


def backtest_panel(profile,mode):
    from learning_lab import load_record,save_record
    from market_data import import_history_csv,demo_market
    from research_data import history
    from strategy_backtest import run
    p=PROFILES[profile]
    st.caption('歷史回測與未來紙上帳戶分開，回測不會增加獲利證據樣本或策略AI訓練筆數。高週期由基準K線完整聚合並按時間向後對齊。')
    with st.form('strategy-backtest-'+profile):
        source=st.radio('策略歷史來源',['目前模式歷史行情','匯入CSV'],horizontal=True)
        file=st.file_uploader('策略基準K線 CSV',type=['csv'],help=f'900–5000根，基準需為{p["interval"]}')
        symbol=st.text_input('策略回測交易對','BTCUSDT').strip().upper()
        a,b,c=st.columns(3)
        fee=a.number_input('回測單邊費率（%）',0.,1.,.05,.01)
        slip=b.number_input('回測單邊滑價（%）',0.,1.,.02,.01)
        funding=c.number_input('回測假設8h資金費（%）',-1.,1.,.01,.01)
        submit=st.form_submit_button('執行此策略歷史重播',type='primary')
    key=f'strategy-backtest/{profile}/{mode}'
    if submit:
        try:
            from market_data import valid_symbol
            if not valid_symbol(symbol):raise ValueError('請填正確USDT合約代號')
            if source=='匯入CSV' and file is None:raise ValueError('請先選擇CSV')
            with st.spinner('重播固定策略、停損停利與成本…'):
                candles=import_history_csv(file.getvalue(),p['interval']) if source=='匯入CSV' else demo_market(symbol,p['interval'],1500)['candles'] if mode=='demo' else history(symbol,p['interval'],mode)
                report=run(candles,profile,symbol,mode,fee,slip,funding)
                report['input_source']='uploaded_csv_unverified' if source=='匯入CSV' else mode
                save_record(STATE_ROOT/'strategy-backtests'/f'{profile}-{mode}.json',report)
                st.session_state[key]=report
        except Exception as exc:
            from binance_client import BinanceAccessError,RatePause
            st.error(str(exc) if isinstance(exc,(ValueError,BinanceAccessError,RatePause)) else '歷史重播暫不可用；原紀錄保留。')
    report=st.session_state.get(key) or load_record(STATE_ROOT/'strategy-backtests'/f'{profile}-{mode}.json')
    if report:
        a,b,c,d=st.columns(4);s=report['stats']
        a.metric('歷史重播交易',s['trades']);b.metric('歷史觀察勝率',f'{s["win_rate"]:.1f}%' if s['win_rate'] is not None else '尚無交易')
        c.metric('歷史1×逐筆淨報酬',f'{s["net_pct"]:+.2f}%');d.metric('歷史逐筆回撤',f'{s["max_drawdown_pct"]:.2f}%')
        st.caption('來源 '+report.get('input_source','未知')+' · 策略 '+report['profile_version'])
        st.line_chart(pd.DataFrame({'歷史單幣權益指數':s['curve']}))
        for note in report['limitations']:st.caption('• '+note)
        if report['trades']:st.dataframe(pd.DataFrame(report['trades']).drop(columns=['context','checks'],errors='ignore').tail(100),hide_index=True,width='stretch')
        st.download_button('下載策略歷史重播報告',json.dumps(report,ensure_ascii=False,indent=2),file_name=f'{profile}-historical-replay.json',mime='application/json')


@st.fragment(run_every=15)
def strategy_page():
    hero('STRATEGIES / SIGNAL & LEARNING','讓每一次進化，都有獲利與風險證據。','市場監控 × 模擬經驗 × 模型競賽。直接看交易點位，也看AI為何升級或保留。',[('趨勢 4h→1h',''),('當沖 1h→15m',''),('僅紙上交易','green')])
    mode=st.selectbox('策略資料模式',['live','demo'],index=1 if os.environ.get('BTC_NAVIGATOR_DEMO')=='1' else 0,format_func=lambda x:'真實資料紙上研究' if x=='live' else '示範／歷史演示')
    db=connect()
    try:
        worker=state(db,'worker')
        if mode=='demo':st.warning('示範模式沒有自動真實市場策略輪詢；可使用下方歷史重播。合成資料不能通過真實獲利研究門檻。')
        elif not worker:st.info('等待策略背景程序；請以新版 START.bat 啟動，並確認全市場取得合約名單。')
        else:
            import time
            age=int(time.time()-worker.get('updated_at',0))
            st.caption(f'策略背景：{worker.get("status")} · 本輪分析 {worker.get("analyzed",0)}／符合成交額範圍 {worker.get("eligible",0)} · 延後 {worker.get("deferred",0)} · 心跳 {age} 秒前')
            if age>240:st.warning('策略心跳超過4分鐘，請查看啟動視窗與scanner.log。')
            for error in worker.get('errors',[])[:4]:st.caption(error)
        all_stats={key:summary(db,key,mode) for key in PROFILES}
        section('策略訊號速覽','DIRECTION · ENTRY · TAKE PROFIT · STOP LOSS')
        only_verified=st.checkbox('只顯示通過獲利與風險研究門檻的策略候選',False)
        cards=[]
        for key,stats in all_stats.items():
            learner=load(db,key,mode);model=learner.get('incumbent')
            closed=[r for r in stats['rows'] if r['status']=='closed']
            proof=evidence(selected_forward(closed,model['id']) if model else [],mode,stats['unresolved'])
            for t in stats['rows']:
                if t['status'] not in ('pending','open'):continue
                qualifies=bool(model and proof['target_pass'] and any(p['model_id']==model['id'] and p['selected'] for p in t.get('model_predictions',[])))
                if model:
                    from ai_diagnostics import guard
                    qualifies=qualifies and not guard(closed,model['id'],t)['blocked']
                if not only_verified or qualifies:cards.append((t,qualifies))
        cards.sort(key=lambda pair:pair[0]['created_at'],reverse=True)
        if cards:
            columns=st.columns(2)
            for index,(t,qualifies) in enumerate(cards[:12]):
                with columns[index%2]:signal_card(t,qualifies)
        else:st.info('目前沒有符合顯示條件的策略紙上候選。WAIT、資料不足或獲利證據不足時，不會填入虛構點位。')
        selected=st.selectbox('查看策略帳戶與紀錄',list(PROFILES),format_func=lambda key:PROFILES[key]['name'])
        stats=all_stats[selected];a=stats['account']
        with st.expander('查看此策略觀望原因與分析條件'):
            query=st.text_input('搜尋策略分析幣種',placeholder='BTC、ETH、SOL…').strip().upper()
            snapshots=[json.loads(r[0]) for r in db.execute('SELECT payload FROM strategy_latest WHERE strategy=? AND mode=?',(selected,mode))]
            filtered=[r for r in snapshots if query in r['symbol']]
            if filtered:
                st.dataframe(pd.DataFrame([{'交易對':r['symbol'],'研究方向':r['side'],'時間UTC':r['signal_time'],
                    '未符合條件':'、'.join(k for k,v in r['checks'].items() if not v)} for r in filtered]).head(500),hide_index=True,width='stretch')
            else:st.caption('尚無符合篩選的策略快照；背景需先取得新鮮行情。')
        tabs=st.tabs(['獲利與風險','AI成長與模型競賽','互動訊號圖表','交易紀錄與復盤','策略歷史重播'])
        with tabs[0]:
            risk_panel(db,selected,mode,stats)
            a1,b,c,d=st.columns(4)
            a1.metric('已結算策略交易',stats['closed']);b.metric('原策略未來觀察勝率',f'{stats["wins"]/stats["closed"]*100:.1f}%' if stats['closed'] else '尚無樣本')
            c.metric('策略帳戶已實現報酬',f'{(a["equity"]/a["initial"]-1)*100:+.2f}%' if a else '尚未建立')
            d.metric('策略帳戶已實現回撤',f'{a["max_drawdown_pct"]:.2f}%' if a else '尚未建立')
            st.caption(f'待進場 {stats["pending"]} · 持倉 {stats["open"]} · 無法還原 {stats["unresolved"]} · 兩策略各自獨立資金，報酬不是兩者合併帳戶；未含未實現損益。')
            if stats['unresolved']:st.error('有未知行情部位，預留資金保留、暫停該策略新進場，不補造績效。請保留資料供還原。')
        with tabs[3]:
            rows=stats['rows']
            if rows:
                table=pd.DataFrame([{'交易編號':r['id'],'交易對':r['symbol'],'類型':PROFILES[selected]['name'],'方向':r['side'],'狀態':r['status'],
                    '參考進場':r.get('entry',r['reference']),'止盈':r['target'],'止損':r['stop'],'保存UTC':r['created_at'],
                    '淨損益':r.get('pnl'),'淨R':r.get('net_r'),'成本版本':r.get('execution_cost',{}).get('version','舊版固定假設'),'資金費來源':r.get('funding_source','未結算／舊版未記來源'),'退出／阻擋原因':r.get('exit_reason') or r.get('reason')} for r in rows])
                st.dataframe(table.tail(200),hide_index=True,width='stretch')
                st.download_button('匯出策略完整交易紀錄',json.dumps(rows,ensure_ascii=False,indent=2),file_name=selected+'-forward-journal.json',mime='application/json')
                identity=st.selectbox('檢視交易分析與依據',[r['id'] for r in reversed(rows)],format_func=lambda value:next(f'{r["symbol"]} · {r["side"]} · {r["status"]} · {r["created_at"]}' for r in rows if r['id']==value))
                trade=next(r for r in rows if r['id']==identity)
                st.json(trade,expanded=False)
                signals=signals_db()
                try:report=signals.execute('SELECT status,text,error,created_at FROM ai_reports WHERE event_id=?',('strategy-'+identity,)).fetchone()
                finally:signals.close()
                if report:
                    inputs=db.execute('SELECT provider,model,payload FROM strategy_ai_inputs WHERE trade_id=?',(identity,)).fetchone()
                    if inputs:
                        st.caption('解讀服務 '+inputs['provider']+' / '+inputs['model'])
                        with st.expander('查看文字模型當時收到的完整資料（無金鑰）'):st.json(json.loads(inputs['payload']))
                    st.caption('文字分析狀態 '+report['status']+' · 分析請求時間（台北） '+pd.to_datetime(report['created_at'],unit='s',utc=True).tz_convert('Asia/Taipei').strftime('%Y-%m-%d %H:%M:%S')+'；不等同預測保存時間')
                    if report['status']=='complete':st.markdown(report['text'])
                else:st.caption('結構化分析已保存；尚無文字摘要。文字解讀需在設定中心啟用，與原訊號共用每日額度。')
            else:st.info('尚無策略預測紀錄，背景只在規則成立時保存候選；不把回測結果冒充未來交易。')
        with tabs[1]:learning_panel(db,selected,mode,stats['rows'])
        with tabs[2]:interactive_signal_panel(stats['rows'],STATE_ROOT,mode)
        with tabs[4]:backtest_panel(selected,mode)
    finally:db.close()

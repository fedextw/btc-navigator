"""Minimal read-only trading surface. Research and model mutations stay backstage."""
import json
import os
import time
from pathlib import Path
import pandas as pd
import streamlit as st
from runtime_config import STATE_ROOT
from signal_store import connect,get_state
from strategy_journal import connect as strategy_db,summary
from strategy_rules import PROFILES
from strategy_learning import load,evidence,selected_forward
from strategy_ui import price
from strategy_growth_ui import signal_chart
from terminal_ui import hero,section,esc
from market_data import INTERVALS,SYMBOLS,valid_symbol
from learning_lab import load_record,save_record
from strategy_risk import number


def signal_state(t,now=None):
    now=pd.Timestamp(now if now is not None else pd.Timestamp.now(tz='UTC'))
    if t['status']=='open':return '模擬持倉','模擬成交',t.get('entry'),False
    if t['status']!='pending':return '非有效候選','參考進場',t.get('reference'),False
    expires=pd.Timestamp(t['eligible_entry_time'])
    if now>=expires:return '參考已過期，等待K線確認','參考進場',t['reference'],False
    return '有效研究候選','參考進場',t['reference'],True


def market_rows(db,mode,now=None):
    now=time.time() if now is None else now
    universe=get_state(db,'universe',{}).get('symbols',[])
    ticker=get_state(db,'tickers',{});quotes=get_state(db,'risk_quotes',{})
    raw=[json.loads(r[0]) for r in db.execute('SELECT payload FROM scan_results WHERE mode=? ORDER BY updated_at DESC',(mode,))]
    by_symbol={}
    for r in raw:by_symbol.setdefault(r['symbol'],r)
    symbols=sorted(set(universe)) if universe else sorted(by_symbol)
    if mode=='demo' and not symbols:symbols=list(SYMBOLS)
    out=[]
    for symbol in symbols:
        r=by_symbol.get(symbol,{})
        mark=quotes.get('marks',{}).get(symbol,{}) if quotes.get('mode','live')==mode else {}
        stamp=number(mark.get('time'));value=number(mark.get('markPrice'),True)
        fresh=bool(value is not None and stamp is not None and 0<=now-stamp/1000<=120)
        if not fresh:
            stamp=number(r.get('mark_time'));value=number(r.get('mark_price'),True)
            fresh=bool(value is not None and stamp is not None and 0<=now-stamp<=120)
            stamp=stamp*1000 if stamp is not None else None
        tick=ticker.get('rows',{}).get(symbol,{}) if mode=='live' else {}
        tf=bool(mode=='live' and 0<=now-ticker.get('fetched_at',0)<=600)
        out.append({'交易對':symbol,'標記價格':value if fresh else None,'24h漲跌%':number(tick.get('priceChangePercent')) if tf else None,
            '24h成交額USDT':number(tick.get('quoteVolume')) if tf else None,'報價狀態':'新鮮' if fresh else '等待／過期',
            '報價時間UTC':str(pd.Timestamp(stamp,unit='ms',tz='UTC')) if fresh else '—','_symbol':symbol})
    return out


def candidate_cards(rows,profile='全部',direction='全部',query='',verified_only=False,now=None):
    out=[]
    for t,qualified in rows:
        status,entry_label,entry,active=signal_state(t,now)
        if not active or t.get('_front_blocked'):continue
        if profile!='全部' and t['strategy']!=profile:continue
        if direction!='全部' and t['side']!=direction:continue
        if query.strip().upper() not in t['symbol']:continue
        if verified_only and not qualified:continue
        out.append((t,qualified))
    return sorted(out,key=lambda pair:pair[0]['created_at'],reverse=True)


def watchlist(root=STATE_ROOT,value=None):
    path=Path(root)/'frontend-watchlist.json'
    if value is not None:
        clean=sorted({v for v in value if valid_symbol(v)})
        save_record(path,{'symbols':clean});return clean
    record=load_record(path) or {}
    if not isinstance(record,dict) or not isinstance(record.get('symbols',[]),list):return []
    return [s for s in record.get('symbols',[]) if valid_symbol(s)]


def front_card(t,qualified):
    status,entry_label,entry,active=signal_state(t)
    side='做多 LONG' if t['side']=='LONG' else '做空 SHORT'
    expires=pd.Timestamp(t['eligible_entry_time']).tz_convert('Asia/Taipei').strftime('%m/%d %H:%M:%S')
    st.markdown(f'''<div class="op-card {'long' if t['side']=='LONG' else 'short'}"><div class="op-top"><span class="op-symbol">{esc(t['symbol'])}</span><span class="pill">{esc(PROFILES[t['strategy']]['name'])} · {esc(side)}</span></div>
<div class="op-price">{esc(entry_label)} {esc(price(entry))}</div>
<div class="front-levels"><span class="up">止盈 <b>{esc(price(t['target']))}</b></span><span class="down">止損 <b>{esc(price(t['stop']))}</b></span></div>
<div class="op-detail">{esc(status)} · 參考有效至 {esc(expires)} 台北<br>{'通過獲利風險研究門檻' if qualified else '模擬研究候選，獲利證據尚待驗證'} · 非實盤成交</div></div>''',unsafe_allow_html=True)


def coin_detail(db,symbol,mode,trades):
    section(symbol,'PRICE · CHART · SIGNAL')
    item=next((r for r in market_rows(db,mode) if r['交易對']==symbol),None)
    if item:
        a,b,c=st.columns(3)
        a.metric('標記價格 USDT',price(item['標記價格']))
        b.metric('24h漲跌',f'{item["24h漲跌%"]:+.2f}%' if item['24h漲跌%'] is not None else '尚無新鮮資料')
        c.metric('24h成交額',f'{item["24h成交額USDT"]:,.0f} USDT' if item['24h成交額USDT'] is not None else '尚無新鮮資料')
        st.caption('報價狀態 '+item['報價狀態']+' · '+item['報價時間UTC'])
    positions=[t for t,_ in trades if t['symbol']==symbol and t['status']=='open']
    if positions:
        st.info('此幣有紙上持倉；持倉紀錄不代表新的入場訊號。詳細損益與風險請看研究後台。')
    selected=[(t,q) for t,q in trades if t['symbol']==symbol]
    if any(t.get('_reference_state') in ('paused','expired') for t,q in selected):st.caption('此幣有先前已暫停或過期的參考訊號，請勿沿用舊點位；等待新的有效候選。')
    candidates=candidate_cards(selected)
    if candidates:
        for t,q in candidates[:4]:front_card(t,q)
    else:st.info('目前沒有有效的新入場候選；不代表市場沒有機會，請等待資料與條件成立。')
    period=st.radio('圖表週期',['15m','1h','4h'],index=1,horizontal=True)
    row=db.execute('SELECT payload FROM scan_cache WHERE symbol=? AND interval=? AND mode=?',(symbol,period,mode)).fetchone()
    if not row:st.info('尚無此週期本機行情，等待背景收集。前台不會自動發起訓練或額外抓取。');return
    f=pd.DataFrame(json.loads(row[0]));f['time']=pd.to_datetime(f.time,utc=True);f['close_time']=pd.to_datetime(f.close_time,utc=True)
    now=pd.Timestamp.now(tz='UTC');f=f[f.close_time<=now].sort_values('time').tail(150)
    if f.empty:st.info('尚無已收盤行情。');return
    last=f.iloc[-1].close_time
    if (now-last).total_seconds()>INTERVALS[period]+120:st.warning('圖表行情已過期，只供查看歷史，不代表目前價格。')
    same=[t for t,q in candidates if t['interval']==period]
    if same:chart=signal_chart(f,same[0])
    else:
        import altair as alt
        base=alt.Chart(f).encode(x=alt.X('time:T',title='UTC'),color=alt.condition('datum.close>=datum.open',alt.value('#54efc3'),alt.value('#ff8ba9')))
        chart=alt.layer(base.mark_rule().encode(y=alt.Y('low:Q',scale=alt.Scale(zero=False),title='USDT'),y2='high:Q'),base.mark_bar(size=5).encode(y='open:Q',y2='close:Q',tooltip=['time:T','open:Q','high:Q','low:Q','close:Q'])).properties(height=320).interactive()
    st.altair_chart(chart,width='stretch');st.caption(f'最後收盤 {last} UTC · 僅顯示已收盤K線；同週期有效訊號才畫入場與止盈止損。')


@st.fragment(run_every=15)
def frontend(page):
    mode='demo' if os.environ.get('BTC_NAVIGATOR_DEMO')=='1' else 'live'
    hero('TRADING / MARKET & SIGNALS','市場與訊號，一眼掌握。','搜尋合約、查看行情，或直接找到有效的趨勢／當沖候選。分析與學習由背景持續處理。',[('Binance USDT 永續',''),('紙上研究','green')])
    if mode=='demo':st.warning('目前為示範模式，不能當成真實行情或下單依據。')
    db=connect();journal=strategy_db()
    try:
        markets=market_rows(db,mode);symbols=[r['交易對'] for r in markets]
        reference_states={r['trade_id']:r['status'] for r in journal.execute('SELECT trade_id,status FROM strategy_reference')}
        trades=[]
        fresh_prices={r['交易對']:r['標記價格'] for r in markets}
        from ai_diagnostics import guard
        for key in PROFILES:
            stats=summary(journal,key,mode);model=load(journal,key,mode).get('incumbent')
            proof=evidence(selected_forward([r for r in stats['rows'] if r['status']=='closed'],model['id']) if model else [],mode,stats['unresolved'])
            for t in stats['rows']:
                if t['status'] not in ('pending','open'):continue
                qualified=bool(model and proof['target_pass'] and any(p['model_id']==model['id'] and p['selected'] for p in t.get('model_predictions',[])))
                ref=reference_states.get(t['id'])
                if t['status']=='pending' and ref in ('paused','expired'):
                    t={**t,'_front_blocked':'參考已暫停或過期','_reference_state':ref}
                if model and t['status']=='pending':
                    safety=guard([r for r in stats['rows'] if r['status']=='closed'],model['id'],t)
                    qualified=qualified and not safety['blocked']
                    if safety['blocked']:t={**t,'_front_blocked':'AI退化／行情適配／不確定性暫停新訊號'}
                if stats['unresolved'] and t['status']=='pending':t={**t,'_front_blocked':'策略有未知部位，暫不顯示新入場候選'}
                if mode=='live' and t['status']=='pending':
                    mark=fresh_prices.get(t['symbol'])
                    if mark is None or abs(mark-t['reference'])>.75*t['atr']:
                        t={**t,'_front_blocked':'報價過期、缺漏或偏離訊號'}
                trades.append((t,qualified))
        active=candidate_cards(trades);scan=get_state(db,'status',{});age=time.time()-scan.get('updated_at',0)
        status='等待／更新過期' if age>180 else scan.get('status','等待')
        st.markdown(f'<div class="front-status"><span>可查詢合約 <b>{len(symbols)}</b></span><span>有效候選 <b>{len(active)}</b></span><span>背景 {esc(status)}</span></div>',unsafe_allow_html=True)
        st.caption('行情每15秒重新讀取本機快取；背景收集速度依交易所與網路狀況。分析與訓練不依賴這個頁面持續開啟。')
        if page=='交易訊號':
            a,b,c=st.columns([2,1,1]);query=a.text_input('搜尋訊號幣種',placeholder='BTC、ETH、SOL…')
            profile=b.selectbox('交易類型',['全部','trend','intraday'],format_func=lambda k:PROFILES[k]['name'] if k in PROFILES else k)
            side=c.selectbox('方向',['全部','LONG','SHORT'])
            verified=st.checkbox('只看通過獲利風險門檻的候選',False)
            cards=candidate_cards(trades,profile,side,query,verified)
            section('有效訊號','ENTRY · TAKE PROFIT · STOP LOSS')
            if not cards:st.info('目前沒有符合篩選的有效候選。已過期或持倉紀錄不作新入場訊號；報價缺漏、AI風險觀察中或篩選條件不符時，也不顯示候選。')
            page_no=st.number_input('訊號頁碼',min_value=1,max_value=max(1,(len(cards)+11)//12),value=1,step=1) if len(cards)>12 else 1
            columns=st.columns(2)
            for i,(t,q) in enumerate(cards[(page_no-1)*12:page_no*12]):
                with columns[i%2]:
                    front_card(t,q)
                    if st.button('查看 '+t['symbol']+' 圖表',key='front-detail-'+t['id']):st.session_state['front_coin']=t['symbol']
        else:
            query=st.text_input('搜尋合約',placeholder='輸入 BTC、ETH，或完整代號')
            favorites=watchlist()
            if page=='自選清單':
                selected=st.multiselect('管理自選合約',symbols,default=[s for s in favorites if s in symbols])
                if st.button('儲存自選清單'):
                    # Keep delisted favorites for visibility rather than silently erasing them.
                    favorites=watchlist(value=selected+[s for s in favorites if s not in symbols]);st.success('自選清單已儲存於本機。')
                visible=[r for r in markets if r['交易對'] in favorites]
                missing=[s for s in favorites if s not in symbols]
                if missing:st.caption('目前不在可查詢名單：'+'、'.join(missing))
            else:visible=markets
            visible=[r for r in visible if query.strip().upper() in r['交易對']]
            st.caption(f'符合 {len(visible)} 個合約；目前範圍為Binance USDT永續，不含所有交易所或現貨。缺資料顯示空白，不補造行情。')
            if visible:
                page_no=st.number_input('行情頁碼',1,max(1,(len(visible)+49)//50),1)
                st.dataframe(pd.DataFrame(visible[(page_no-1)*50:page_no*50]).drop(columns='_symbol'),hide_index=True,width='stretch')
            else:st.info('沒有符合的合約；若名單尚未載入，請確認背景與交易所連線。')
        # Always offer explicit lookup, including from a signal card.
        lookup=sorted(set(symbols)|{t['symbol'] for t,q in trades})
        previous=st.session_state.pop('front_coin',None)
        if previous in lookup:st.session_state['front_lookup']=previous
        chosen=st.selectbox('查詢交易對',lookup,index=None,key='front_lookup',placeholder='輸入幣種搜尋，選取後查看行情與訊號')
        if chosen:coin_detail(db,chosen,mode,trades)
        st.caption('訊號為紙上研究候選，不保證獲利，不會自動真實下單。研究後台可查看完整依據、紀錄、風險與設定。')
    finally:db.close();journal.close()

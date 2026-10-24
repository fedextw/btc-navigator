"""Public quote valuation and explicit snapshot cost assumptions. No orders."""
import math
import time
import pandas as pd


def number(value,positive=False):
    try:
        n=float(value)
        return n if math.isfinite(n) and (not positive or n>0) else None
    except (ValueError,TypeError):return None


def quote(mark,book,now=None):
    now=time.time() if now is None else now
    price=number(mark.get('markPrice'),True);stamp=number(mark.get('time'))
    valid=price is not None and stamp is not None and 0<=now-stamp/1000<=120
    bid,ask=number(book.get('bidPrice'),True),number(book.get('askPrice'),True)
    bt=number(book.get('time'));bq,aq=number(book.get('bidQty'),True),number(book.get('askQty'),True)
    book_valid=bool(bid and ask and bid<=ask and bt is not None and 0<=now-bt/1000<=120 and bq and aq)
    spread=(ask-bid)/((ask+bid)/2)*100 if book_valid else None
    return {'mark':price if valid else None,'mark_time':stamp/1000 if valid else None,
            'book_valid':book_valid,'spread_pct':spread,'bid':bid if book_valid else None,'ask':ask if book_valid else None,
            'bid_qty':bq if book_valid else None,'ask_qty':aq if book_valid else None,
            'book_time':bt/1000 if book_valid else None}


def snapshot_cost(q,side,slippage,reference,atr,quantity):
    now=time.time()
    if not q.get('mark_time') or not q.get('book_time') or not 0<=now-q['mark_time']<=120 or not 0<=now-q['book_time']<=120:return None,'報價缺漏或超過120秒，暫停新候選'
    if not q['book_valid'] or q['mark'] is None:return None,'報價缺漏或超過120秒，暫停新候選'
    if q['spread_pct']>.5:return None,'買賣價差超過0.5%，暫停新候選'
    if abs(q['mark']-reference)>.75*atr:return None,'新鮮標記價格已偏離訊號0.75ATR'
    visible=q['ask_qty'] if side=='LONG' else q['bid_qty']
    participation=quantity/visible if visible else float('inf')
    # Top-of-book is not depth. Refuse fills larger than visible size, don't invent VWAP.
    if participation>1:return None,'模擬數量超過當時可見首檔數量，無法估算完整成交'
    half=q['spread_pct']/2
    return {'version':'quote-snapshot-v1','half_spread_pct':half,'base_slippage_pct':slippage,
            'effective_slippage_pct':slippage+half,'top_book_participation':participation,
            'quote':q,'note':'預測保存時快照；雙邊沿用半價差加設定滑價作成本壓測，非未來成交報價或完整深度撮合'},None


def value_positions(rows,account,quotes,now=None):
    now=time.time() if now is None else now
    details=[];floating=0.;notional=0.;stop_risk=0.;unknown=0;long=0.;short=0.
    for t in rows:
        if t['status'] not in ('pending','open','unresolved'):continue
        item={'交易對':t['symbol'],'方向':t['side'],'狀態':t['status'],'浮動損益':None,'名目曝險':None,'距止損%':None,'原因':''}
        if t['status']=='pending':item['原因']='待進場，僅保留資金';details.append(item);continue
        q=quotes.get(t['symbol'],{});mark=q.get('mark');stamp=q.get('mark_time')
        if t['status']=='unresolved' or mark is None or stamp is None or not 0<=now-stamp<=120 or not t.get('entry'):
            unknown+=1;item['原因']='未知成交路徑或報價缺漏／過期，不能填0';details.append(item);continue
        direction=1 if t['side']=='LONG' else -1;qty=t['quantity'];exposure=qty*mark
        pnl=direction*qty*(mark-t['entry'])
        exit_fee=exposure*t['fee_pct']/100
        # Entry fees already debited in realized account, do not subtract again.
        estimated_close=pnl-exit_fee-exposure*t['slippage_pct']/100
        floating+=estimated_close;notional+=exposure
        if direction>0:long+=exposure
        else:short+=exposure
        gap=direction*(mark-t['stop'])/mark*100
        stop_risk+=max(0,direction*qty*(mark-t['stop']))
        item.update({'浮動損益':estimated_close,'名目曝險':exposure,'距止損%':gap,'原因':'標記價已越過止損，待K線確認' if gap<=0 else '按標記價估值'})
        details.append(item)
    equity=account['equity'] if account else None
    return {'positions':details,'unknown':unknown,'known_floating':floating,'floating':None if unknown else floating,
            'estimated_equity':equity+floating if equity is not None and not unknown else None,
            'gross_exposure':None if unknown else notional,'known_exposure':notional,'long':long,'short':short,
            'direction_concentration_pct':max(long,short)/notional*100 if notional else None,
            'to_stop_loss':None if unknown else stop_risk,
            'note':'浮盈虧扣估計出場費與滑價；進場費已在已實現帳戶扣除，不重扣。未計尚未結算資金費、強平、深度撮合；方向集中度不是相關係數。'}


def funding_history(client,symbol,start,now):
    begin=pd.Timestamp(start);end=pd.Timestamp(now)
    data=client.json('/fapi/v1/fundingRate',{'symbol':symbol,'startTime':int(begin.timestamp()*1000),'endTime':int(end.timestamp()*1000),'limit':1000},weight=1)
    if not isinstance(data,list) or len(data)>=1000:raise ValueError('資金費歷史範圍不完整')
    events={}
    for row in data:
        when=number(row.get('fundingTime'));rate=number(row.get('fundingRate'));price=number(row.get('markPrice'),True)
        if row.get('symbol')!=symbol or when is None or rate is None or price is None or not begin.timestamp()*1000<=when<=end.timestamp()*1000:raise ValueError('資金費紀錄不完整')
        if when in events and events[when]!=[rate,price]:raise ValueError('重複資金費資料矛盾')
        events[when]=[rate,price]
    return {'symbol':symbol,'start':str(begin),'end':str(end),'observed_at':str(pd.Timestamp.now(tz='UTC')),
            'events':[{'time':str(pd.Timestamp(ts,unit='ms',tz='UTC')),'rate':v[0],'mark':v[1]} for ts,v in sorted(events.items())]}


def correlation_pairs(rows,frames,now=None):
    now=pd.Timestamp(now if now is not None else pd.Timestamp.now(tz='UTC'))
    active={r['symbol']:r for r in rows if r['status']=='open'}
    returns={}
    for symbol in active:
        f=frames.get(symbol)
        if f is None or len(f)<31:continue
        f=f.copy();f['time']=pd.to_datetime(f.time,utc=True);f['close_time']=pd.to_datetime(f.close_time,utc=True)
        f=f[f.close_time<=now].sort_values('time').tail(121)
        if len(f)<31 or not 0<=(now-f.iloc[-1].close_time).total_seconds()<=7200:continue
        if not (f.time.diff().dropna().dt.total_seconds()==3600).all() or not (f.close>0).all():continue
        returns[symbol]=f.set_index('time').close.pct_change().dropna()
    result=[]
    symbols=sorted(returns)
    for i,a in enumerate(symbols):
        for b in symbols[i+1:]:
            aligned=pd.concat([returns[a],returns[b]],axis=1,join='inner').dropna()
            if len(aligned)<30 or (aligned.std()==0).any():continue
            corr=float(aligned.corr().iloc[0,1]);signed=corr*(1 if active[a]['side']==active[b]['side'] else -1)
            if not math.isfinite(corr):continue
            result.append({'交易對A':a,'交易對B':b,'同時段樣本':len(aligned),'報酬相關':corr,'方向調整相關':signed,'共同方向風險偏高':signed>=.8})
    return result

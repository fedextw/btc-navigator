"""Rate-budgeted full-universe strategy paper worker; no exchange order endpoints."""
import json
import time
import pandas as pd
from strategy_rules import PROFILES
from strategy_journal import connect,process,state,summary
from strategy_learning import update,evidence,selected_forward
from strategy_patterns import discover
from signal_store import connect as signals_db,get_state
from monitor_settings import load_settings
from binance_client import RatePause
from runtime_config import STATE_ROOT


def risk_settings(settings):
    return {'initial':settings['strategy_initial'],'risk_pct':settings['strategy_risk_pct'],
        'max_positions':settings['strategy_max_positions'],'daily_loss_pct':settings['strategy_daily_loss_pct'],
        'fee_pct':settings['strategy_fee_pct'],'slippage_pct':settings['strategy_slippage_pct'],
        'funding_pct_8h':settings['strategy_funding_pct_8h']}


def source_context(root):
    from collector import connect as research_db
    db=research_db(root)
    try:
        news=[dict(title=r[0],url=r[1],source=r[2],published=r[3],observed_at=r[4]) for r in db.execute('SELECT title,url,source,published,first_observed_at FROM news ORDER BY first_observed_at DESC LIMIT 8')]
        row=db.execute('SELECT observed_at,payload FROM market_context ORDER BY observed_at DESC LIMIT 1').fetchone()
        return {'news':news,'market':json.loads(row[1]) if row else {},'market_observed_at':row[0] if row else None,
            'note':'這些是保存預測當下可見的新聞標題／背景，不會用出場後資訊回填'}
    finally:db.close()


def cycle(service,root=STATE_ROOT):
    settings=load_settings(root);db=connect(root);signals=signals_db(root)
    mode='demo' if service.demo else 'live';prior=state(db,'worker')
    status={'status':'研究中','mode':mode,'updated_at':time.time(),'analyzed':0,'failed':0,'deferred':0,'errors':[]}
    try:
        if not settings['strategy_enabled']:status['status']='已暫停';return status
        universe=get_state(signals,'universe',{}).get('symbols',[])
        ticker=get_state(signals,'tickers',{})
        if not universe:status['status']='等待全市場合約名單';return status
        quotes=ticker.get('rows',{})
        fresh=time.time()-ticker.get('fetched_at',0)<=600
        eligible=[s for s in universe if fresh and float(quotes.get(s,{}).get('quoteVolume',0))>=settings['min_volume_usdt']]
        holding=[r[0] for r in db.execute("SELECT DISTINCT symbol FROM strategy_trades WHERE mode=? AND status IN ('pending','open','unresolved')",(mode,))]
        symbols=sorted(set(eligible)|set(holding));status['universe']=len(universe);status['eligible']=len(symbols)
        if not symbols:status['status']='等待新鮮成交額或符合門檻幣種';return status
        offset=int(prior.get('cursor',0))%len(symbols)
        ordered=symbols[offset:]+symbols[:offset]
        archived=source_context(root)
        for index,symbol in enumerate(ordered):
            frames={};paused=False
            for period in ('1h','4h','15m'):
                frame=service.frame_from_cache(signals,symbol,period)
                if frame is None:
                    budget=service.client.budget
                    # Keep part of the shared minute budget available for primary scanning.
                    if budget.clock()-budget.window<60 and budget.used>=budget.limit*.75:
                        paused=True;break
                    try:
                        frame=service.fetch_frame(symbol,period)
                        signals.execute('INSERT OR REPLACE INTO scan_cache VALUES (?,?,?,?)',(symbol,period,mode,frame.to_json(orient='records',date_format='iso')))
                        signals.commit()
                    except RatePause:paused=True;break
                    except Exception as exc:
                        status['failed']+=1;status['errors'].append(symbol+'/'+period+': '+type(exc).__name__)
                        continue
                frames[period]=frame
            if paused:
                status['deferred']=len(ordered)-index;status['cursor']=(offset+index)%len(symbols);break
            for key,p in PROFILES.items():
                if p['interval'] not in frames:continue
                base=frames[p['interval']]
                last=db.execute('SELECT payload FROM strategy_latest WHERE strategy=? AND symbol=? AND mode=?',(key,symbol,mode)).fetchone()
                unknown=db.execute("SELECT COUNT(*) FROM strategy_trades WHERE strategy=? AND symbol=? AND mode=? AND status='unresolved'",(key,symbol,mode)).fetchone()[0]
                if last and not unknown and pd.Timestamp(json.loads(last[0])['signal_time'])==base.iloc[-1].close_time:continue
                if unknown:
                    recovery_key=f'recovery/{key}/{symbol}/{mode}'
                    attempt=state(db,recovery_key)
                    if time.time()-attempt.get('attempted_at',0)>=600:
                        state(db,recovery_key,{'attempted_at':time.time()})
                        try:
                            from market_data import validate_candles
                            base=validate_candles(service.client.json('/fapi/v1/klines',{'symbol':symbol,'interval':p['interval'],'limit':1500},weight=10))
                        except Exception:
                            pass  # Keep the unknown reservation; never synthesize a path.
                higher=frames.get(p['higher'],base.iloc[:0].copy())
                try:
                    local_context={**archived,'ticker_fresh':fresh,'volume_24h':quotes.get(symbol,{}).get('quoteVolume')}
                    # Out-of-universe holdings are settled but never create another order.
                    profile_risk=risk_settings(settings)
                    plan=process(db,base,higher,key,symbol,mode,profile_risk,context=local_context,allow_new=symbol in eligible)
                    from strategy_alerts import emit
                    emit(db,signals,plan,settings)
                except Exception as exc:
                    status['failed']+=1;status['errors'].append(symbol+'/'+key+': '+type(exc).__name__)
            status['analyzed']+=1
            status['cursor']=(offset+index+1)%len(symbols)
            if status['analyzed']%10==0 or time.time()-status['updated_at']>=15:
                status['updated_at']=time.time();state(db,'worker',status)
        for profile in PROFILES:
            learner=update(db,profile,mode)
            count=learner.get('closed_samples',0)
            key=f'patterns_count/{profile}/{mode}'
            old=state(db,key)
            if count>=60 and old.get('count')!=count:
                closed=[json.loads(r[0]) for r in db.execute("SELECT payload FROM strategy_trades WHERE strategy=? AND mode=? AND status='closed'",(profile,mode))]
                report=discover(closed,mode)
                db.execute('INSERT OR IGNORE INTO strategy_reviews VALUES (?,?,?,?,?)',(report['id'],profile,mode,report['created_at'],json.dumps(report,ensure_ascii=False,allow_nan=False)))
                db.commit();state(db,key,{'count':count})
        status['status']='部分完成' if status['failed'] or status['deferred'] else '完成'
    except Exception as exc:
        db.rollback();status['status']='研究暫不可用';status['errors'].append(type(exc).__name__)
    finally:
        status['updated_at']=time.time();status['errors']=status['errors'][:8];state(db,'worker',status)
        db.close();signals.close()
    return status


def loop(root,client,stopped):
    from scanner import MarketScanner
    service=MarketScanner(root,client)
    while not stopped.is_set():
        try:
            cycle(service,root)
        except Exception as exc:
            db=connect(root)
            try:state(db,'worker',{'status':'研究暫不可用','mode':'live','updated_at':time.time(),'errors':[type(exc).__name__]})
            finally:db.close()
        stopped.wait(30)

"""Optional commentary on the immutable pre-entry journal, sharing the daily quota."""
from datetime import datetime
import json
import os
import time
from zoneinfo import ZoneInfo
import pandas as pd
from ai_research import summarize
from monitor_settings import load_settings,load_credentials
from strategy_journal import connect as journal_db


def generate(db,root,summarizer=summarize):
    settings=load_settings(root)
    if not settings['auto_ai_enabled'] or not settings['strategy_ai_enabled']:return 'disabled'
    credentials=load_credentials(root) if settings['ai_provider']=='openai' else {}
    key=(os.environ.get('AI_API_KEY') or credentials.get('ai_api_key')) if settings['ai_provider']=='openai' else None
    if settings['ai_provider']=='openai' and not key:return 'missing_ai_key'
    journal=journal_db(root)
    try:
        candidates=journal.execute("SELECT id,payload FROM strategy_trades WHERE mode='live' AND status IN ('pending','open') ORDER BY signal_time DESC LIMIT 100").fetchall()
    finally:journal.close()
    day=datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat()
    db.execute('BEGIN IMMEDIATE')
    if db.execute('SELECT COUNT(*) FROM ai_reports WHERE day=?',(day,)).fetchone()[0]>=settings['ai_daily_limit']:
        db.rollback();return 'daily_limit'
    selected=next((row for row in candidates if not db.execute('SELECT 1 FROM ai_reports WHERE event_id=?',('strategy-'+row['id'],)).fetchone()),None)
    if not selected:db.rollback();return 'no_strategy_pending'
    identity='strategy-'+selected['id'];plan=json.loads(selected['payload'])
    db.execute('INSERT INTO ai_reports VALUES (?,?,?,?,?,?)',(identity,day,'running',None,None,time.time()));db.commit()
    context=plan.get('analysis_context',{})
    result={'frame':pd.DataFrame([{'close_time':plan['signal_time']}]),'score':0,'side':plan['side'],
        'factors':[{'name':k,'score':0,'evidence':'通過' if v else '未通過'} for k,v in plan['checks'].items()],
        'reasons':['紙上策略研究，不代表正式下單指令或獲利保證','只能解讀預測保存時的快照，不能引用已知後續結果'],
        'strategy_context':{k:plan.get(k) for k in ('strategy','profile_version','reference','stop','target','created_at','eligible_entry_time','context','assumptions','model_predictions')}}
    try:
        journal=journal_db(root)
        try:
            with journal:
                archived={'strategy_context':result['strategy_context'],'factors':result['factors'],
                    'reasons':result['reasons'],'news':context.get('news',[]),'market_context':context.get('market',{})}
                journal.execute('INSERT OR IGNORE INTO strategy_ai_inputs VALUES (?,?,?,?,?)',
                    (plan['id'],str(pd.Timestamp.now(tz='UTC')),settings['ai_provider'],settings['ollama_model'] if settings['ai_provider']=='ollama' else os.environ.get('AI_MODEL','gpt-4.1-mini'),json.dumps(archived,ensure_ascii=False,allow_nan=False)))
        finally:journal.close()
        text=summarizer({'symbol':plan['symbol'],'interval':plan['interval'],'mode':'live'},result,context.get('news',[]),key,context.get('market',{}),provider=settings['ai_provider'],model=settings['ollama_model'])
        db.execute("UPDATE ai_reports SET status='complete',text=? WHERE event_id=?",(text,identity));db.commit();return 'complete'
    except Exception as exc:
        db.execute("UPDATE ai_reports SET status='failed',error=? WHERE event_id=?",(type(exc).__name__,identity));db.commit();return 'failed'

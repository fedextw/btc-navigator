"""Versioned, point-in-time context. Missing is masked; no outcome text or LLM scores."""
import math
import re
import pandas as pd

NAMES=['news_count','news_sources','headline_word_balance','news_available','funding_pct','funding_available',
       'oi_change_pct','oi_available','fear_greed','fear_available','stablecoin_change','stablecoin_available','market_change','market_available']
VERSION='context-asof-v1'


def timestamp(value):
    try:
        t=pd.Timestamp(value)
        return t if pd.notna(t) and t.tzinfo is not None else None
    except (ValueError,TypeError):return None


def recent(value,now,seconds):
    t=timestamp(value)
    return t is not None and 0<=(now-t).total_seconds()<=seconds


def numeric(value):
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None


def extract(plan):
    now=timestamp(plan.get('created_at',plan.get('observed_at')))
    out=dict.fromkeys(NAMES,0.);sources=[]
    if now is None:return {'version':VERSION,'values':out,'sources':[],'note':'缺少可信的預測保存時間'}
    c=plan.get('analysis_context',{});seen=set();titles=[];names=set()
    for item in c.get('news',[])[:50]:
        if not recent(item.get('observed_at'),now,86400) or not recent(item.get('published'),now,86400):continue
        key=item.get('url') or item.get('title')
        if not key or key in seen:continue
        seen.add(key);titles.append(str(item.get('title','')));names.add(item.get('source','unknown'))
    if titles:
        text=' '.join(titles).lower();pos=len(re.findall(r'\b(?:approval|inflow|rally|surge|adoption)\b',text));neg=len(re.findall(r'\b(?:hack|outflow|ban|lawsuit|crash)\b',text))
        out.update(news_count=min(len(titles),50)/50,news_sources=min(len(names),10)/10,headline_word_balance=(pos-neg)/max(1,pos+neg),news_available=1.)
        sources.append('事前已觀測且已發布的24h新聞標題；固定英文詞彙計數不是LLM情緒判斷')
    e=c.get('exchange',{})
    if recent(e.get('observed_at'),now,600):
        for key,mask in [('funding_pct','funding_available')]:
            value=numeric(e.get(key))
            if value is not None:out[key]=max(-10,min(10,value))/10;out[mask]=1.
    oi=c.get('oi_snapshot',{})
    if recent(oi.get('observed_at'),now,600) and numeric(oi.get('oi_change_pct')) is not None:
        out['oi_change_pct']=max(-10,min(10,numeric(oi['oi_change_pct'])))/10;out['oi_available']=1.
    market=c.get('market',{})
    if recent(c.get('market_observed_at'),now,1800) and recent(market.get('fetched_at'),now,1800):
        data=market.get('data',{})
        for source,key,name,mask,scale in [('Alternative.me','fear_greed','fear_greed','fear_available',100),('DefiLlama Stablecoins','change_7_samples_pct','stablecoin_change','stablecoin_available',100),('CoinGecko','market_cap_change_24h_pct','market_change','market_available',100)]:
            item=data.get(source,{})
            value=numeric(item.get(key))
            if not item.get('stale',False) and recent(item.get('as_of'),now,3*86400) and value is not None:
                out[name]=max(-2,min(2,value/scale));out[mask]=1.
    return {'version':VERSION,'values':out,'sources':sources,'as_of':str(now),
            'note':'全球新聞／穩定幣供給為背景代理，不是單幣淨資金流。缺漏保留0值與獨立可用遮罩；不回填舊預測。'}

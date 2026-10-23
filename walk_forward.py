"""Expanding-window train/validation/test, with purged labels at EVERY boundary.

Fixed grids are selected on past validation only. Test folds are disjoint.
Regime variant is a fixed filter of baseline entries, not a hindsight optimizer.
"""
from datetime import datetime, timezone
import hashlib
import numpy as np
import pandas as pd
from learning_lab import feature_frame, FEATURES, fit_classifier, predict, simulate, trade_stats
from market_regime import regime_frame, LABELS
from market_data import INTERVALS

VERSION=1


def evaluate(candles,symbol,interval,demo=False,horizon=6,fee_pct=.05,slippage_pct=.02):
    if interval not in INTERVALS or horizon not in (3,6,12) or not (0<=fee_pct<=1 and 0<=slippage_pct<=1):
        raise ValueError('滾動驗證參數不正確')
    if len(candles)<800 or not (candles.time.diff().dropna().dt.total_seconds()==INTERVALS[interval]).all():
        raise ValueError('滾動驗證至少需要 800 根連續已收盤 K 線')
    frame=feature_frame(candles)
    labels=regime_frame(candles)[['close_time','regime']]
    frame=frame.merge(labels,on='close_time',how='left',validate='one_to_one')
    n=len(frame); starts=np.linspace(n//2,n,4,dtype=int)
    x=frame[FEATURES].to_numpy(dtype=float)
    y=(frame.close.shift(-horizon)/frame.open.shift(-1)-1>0).astype(float).to_numpy()
    cost=2*(fee_pct+slippage_pct)/100
    folds=[]; all_trades=[]; filtered=[]; squared=[]; baseline_squared=[]
    for fold,(test_start,test_end) in enumerate(zip(starts[:-1],starts[1:]),1):
        train_end=int(test_start*.8)
        train_stop=train_end-horizon
        validation_stop=test_start-horizon
        test_stop=test_end-horizon
        if min(train_stop,validation_stop-train_end,test_stop-test_start)<=0:
            raise ValueError('分段樣本不足')
        best=None
        for regularization in (.001,.01,.1):
            model=fit_classifier(x[:train_stop],y[:train_stop],regularization)
            probabilities=predict(model,x[:test_start])
            for threshold in (.55,.60,.65):
                stats=trade_stats(simulate(frame,probabilities,train_end,validation_stop,horizon,threshold,cost))
                merit=stats['net_pct']-.5*stats['max_drawdown_pct'] if stats['trades']>=5 else -1e9
                if best is None or merit>best[0]:
                    best=(merit,model,threshold,regularization,stats)
        _,model,threshold,regularization,validation=best
        p=predict(model,x[test_start:test_end])
        # simulate uses absolute indices; earlier values are never consulted.
        probabilities=np.r_[np.full(test_start,.5),p]
        trades=simulate(frame.iloc[:test_end],probabilities,test_start,test_stop,horizon,threshold,cost)
        regime_lookup=dict(zip(frame.close_time,frame.regime))
        for trade in trades:
            trade.update(fold=fold,regime=regime_lookup[pd.Timestamp(trade['signal_time'])])
        subset=[t for t in trades if (t['regime']=='trend_up' and t['side']=='LONG') or (t['regime']=='trend_down' and t['side']=='SHORT')]
        stats=trade_stats(trades); variant=trade_stats(subset)
        actual=y[test_start:test_stop]
        predicted=p[:test_stop-test_start]
        prior=float(y[:train_stop].mean())
        errors=(predicted-actual)**2; fixed=(prior-actual)**2
        squared.extend(errors.tolist()); baseline_squared.extend(fixed.tolist())
        folds.append({'fold':fold,'train_first':str(frame.iloc[0].time),
            'train_last_signal':str(frame.iloc[train_stop-1].close_time),
            'train_last_outcome':str(frame.iloc[train_stop-1+horizon].close_time),
            'validation_first':str(frame.iloc[train_end].close_time),
            'validation_last_outcome':str(frame.iloc[validation_stop-1+horizon].close_time),
            'test_first':str(frame.iloc[test_start].close_time),
            'test_last_signal':str(frame.iloc[test_stop-1].close_time),
            'test_last_outcome':str(frame.iloc[test_end-1].close_time),
            'threshold':threshold,'regularization':regularization,'validation_trades':validation['trades'],
            'model':model,'baseline':stats,'regime_filter':variant,
            'brier':float(errors.mean()),'baseline_brier':float(fixed.mean())})
        all_trades.extend(trades);filtered.extend(subset)
    baseline=trade_stats(all_trades);variant=trade_stats(filtered)
    checks={'真實行情而非示範':not demo,'每段驗證交易至少五筆':all(f['validation_trades']>=5 for f in folds),
        '每段測試交易至少五筆':all(f['baseline']['trades']>=5 for f in folds),
        '合計未見交易至少三十筆':baseline['trades']>=30,
        '至少兩段扣費後正報酬':sum(f['baseline']['net_pct']>0 for f in folds)>=2,
        '合計平均淨報酬為正':baseline['expectancy_pct'] is not None and baseline['expectancy_pct']>0,
        '合計 Profit factor 至少 1.1':baseline['profit_factor'] is not None and baseline['profit_factor']>=1.1,
        '合計回撤低於15%':baseline['max_drawdown_pct']<15,
        '機率誤差優於各段訓練比例基準':np.mean(squared)<np.mean(baseline_squared)}
    regimes=[{'code':code,'label':label,**trade_stats([t for t in all_trades if t['regime']==code])} for code,label in LABELS.items() if code!='insufficient']
    digest=hashlib.sha256(candles.to_csv(index=False).encode()).hexdigest()
    return {'version':VERSION,'id':hashlib.sha256(f'{symbol}/{interval}/{demo}/{digest}/{horizon}/{cost}/{VERSION}'.encode()).hexdigest()[:20],
        'symbol':symbol,'interval':interval,'demo':demo,'created_at':datetime.now(timezone.utc).isoformat(),
        'dataset_sha256':digest,'horizon':horizon,'cost':cost,'folds':folds,'baseline':baseline,
        'regime_filter':variant,'regimes':regimes,'trades':all_trades,'checks':{k:bool(v) for k,v in checks.items()},
        'evidence_pass':bool(all(checks.values())),'shadow_only':True,
        'brier':float(np.mean(squared)),'baseline_brier':float(np.mean(baseline_squared)),
        'limitations':['單幣 1× 固定持有期，含雙邊費用與滑價，不含資金費、強平或真實撮合',
            '三段擴展視窗，舊測試期在之後分段可成為已知歷史；分段測試績效不重複計算',
            '行情變體僅篩選基準交易；沒有驗證多週期歷史策略，不能據此宣稱多週期更準',
            '滾動結果是影子研究，不修改正式訊號或自動晉升門檻']}

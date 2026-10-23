"""Forward-only profit research and paired model comparisons, never account P&L."""
import math
import numpy as np
import pandas as pd

OBJECTIVE = 'profit-risk-v2'


def forward_window(rows, now=None):
    now = pd.Timestamp(now if now is not None else pd.Timestamp.now(tz='UTC'))
    valid = []
    for row in rows:
        if row.get('status') != 'closed':
            continue
        try:
            exit_at = pd.Timestamp(row['exit_time'])
            known_at = max(exit_at, pd.Timestamp(row.get('settled_at', row['exit_time'])))
            if not now-pd.Timedelta(days=90) <= exit_at <= known_at <= now:
                continue
            if not all(math.isfinite(float(row[k])) for k in ('pnl', 'net_return')):
                continue
            valid.append(row)
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(valid, key=lambda r: (pd.Timestamp(r['exit_time']), r['id']))[-200:]


def daily_interval(rows, values):
    """Resample Taipei exit-day clusters; report mean per opportunity, not portfolio ROI."""
    days = {}
    for row, value in zip(rows, values):
        day = pd.Timestamp(row['exit_time']).tz_convert('Asia/Taipei').strftime('%Y-%m-%d')
        total, count = days.get(day, (0., 0))
        days[day] = (total + float(value), count + 1)
    if len(days) < 2:
        return [None, None]
    totals, counts = np.asarray(list(days.values()), dtype=float).T
    rng = np.random.default_rng(731)
    indices = rng.integers(0, len(days), size=(1200, len(days)))
    means = totals[indices].sum(axis=1) / counts[indices].sum(axis=1)
    return [float(x) for x in np.quantile(means, [.025, .975])]


def risk_score(row):
    """Actual net R normalizes heterogeneous stops and sizing. Missing R is unknown."""
    try:
        value = float(row['net_r'])
        return value if math.isfinite(value) else None
    except (KeyError, TypeError, ValueError):
        return None


def r_drawdown(values):
    curve = np.r_[0., np.cumsum(values)]
    return float(np.max(np.maximum.accumulate(curve) - curve))


def compare(rows, old_id, new_id, mode, unresolved=0, now=None):
    common = [r for r in forward_window(rows, now) if {old_id, new_id}.issubset(
        {p['model_id'] for p in r.get('model_predictions', [])}) and risk_score(r) is not None]
    values = {}
    reports = {}
    for name, identity in [('現行模型', old_id), ('挑戰模型', new_id)]:
        selected = [any(p['model_id'] == identity and p['selected'] for p in r['model_predictions']) for r in common]
        scores = [risk_score(r) if take else 0. for r, take in zip(common, selected)]
        values[identity] = scores
        taken = [v for v, take in zip(scores, selected) if take]
        reports[name] = {'model_id': identity, 'selected': sum(selected), 'opportunities': len(common),
                         'total_r': float(sum(scores)), 'mean_r_per_opportunity': float(np.mean(scores)) if scores else None,
                         'max_drawdown_r': r_drawdown(scores),
                         'win_rate': sum(v > 0 for v in taken)/len(taken)*100 if taken else None}
    delta = [new-old for old, new in zip(values[old_id], values[new_id])]
    interval = daily_interval(common, delta)
    old, new = reports.values()
    days = len({pd.Timestamp(r['exit_time']).tz_convert('Asia/Taipei').date() for r in common})
    checks = {'共同未來機會至少100筆': len(common) >= 100,
              '兩模型各至少選擇100筆': min(old['selected'], new['selected']) >= 100,
              '共同結算至少20個交易日': days >= 20,
              '日群聚差異區間下限大於0R': interval[0] is not None and interval[0] > 0,
              '新模型累計淨R較高': new['total_r'] > old['total_r'],
              '新模型R回撤不高於舊模型': new['max_drawdown_r'] <= old['max_drawdown_r'],
              '真實資料且無待還原交易': mode == 'live' and unresolved == 0}
    return {'objective': OBJECTIVE, 'as_of': str(pd.Timestamp(now if now is not None else pd.Timestamp.now(tz='UTC'))), 'models': reports, 'common': len(common), 'days': days,
            'delta_mean_r': float(np.mean(delta)) if delta else None, 'delta95_r': interval,
            'checks': {k: bool(v) for k, v in checks.items()}, 'comparison_pass': all(checks.values()),
            'curve': [{'時間': r['exit_time'], '現行模型': float(a), '挑戰模型': float(b)}
                      for r, a, b in zip(common, np.cumsum(values[old_id]), np.cumsum(values[new_id]))],
            'note': '共同已結算機會，未選擇記0R；費用已計入。淨R為逐筆等風險研究指標，非可成交組合報酬；未結算交易未計入。日群聚區間仍未涵蓋跨日相關及反覆檢驗偏誤。'}

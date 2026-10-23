"""Retrospective capital-constrained replay of closed forward-paper trades.

Scenario assumptions, not exchange fills. Keeps the original fixed-horizon exits.
No model selection, journal rewriting, leverage, stops or fabricated funding data.
"""
from datetime import datetime
import heapq
import math


def replay(rows, initial=10000.0, allocation_pct=10.0, max_positions=5,
           fee_pct=.05, slippage_pct=.02, spread_pct=.02, funding_pct_8h=.01):
    parameters = [initial, allocation_pct, max_positions, fee_pct, slippage_pct, spread_pct, funding_pct_8h]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in parameters):
        raise ValueError('參數必須是有限數值')
    if not (initial > 0 and 0 < allocation_pct <= 100 and isinstance(max_positions, int) and 1 <= max_positions <= 20
            and all(0 <= v <= 1 for v in (fee_pct, slippage_pct, spread_pct)) and -1 <= funding_pct_8h <= 1):
        raise ValueError('資金或成本參數超出範圍')
    trades, excluded = [], 0
    for row in rows:
        if row.get('status') != 'closed':
            excluded += 1
            continue
        try:
            start = datetime.fromisoformat(row['entry_time'])
            end = datetime.fromisoformat(row['exit_time'])
            entry, exit_price = float(row['entry']), float(row['exit'])
            if start.tzinfo is None or end.tzinfo is None or start >= end or min(entry, exit_price) <= 0 or not all(map(math.isfinite, (entry, exit_price))) or row['side'] not in ('LONG', 'SHORT'):
                raise ValueError('invalid trade')
            trades.append({**row, 'entry': entry, 'exit': exit_price, '_start': start.timestamp(), '_end': end.timestamp()})
        except (ValueError, TypeError, KeyError):
            excluded += 1
    trades.sort(key=lambda t:(t['_start'], t['symbol'], t.get('signal_time', '')))
    equity, free = initial, initial
    opened, symbols, completed, curve = [], set(), [], [{'時間':'起始','已實現權益':initial}]
    skipped = 0
    sequence = 0
    peak, drawdown = initial, 0.0
    def settle(until):
        nonlocal equity, free, peak, drawdown
        while opened and opened[0][0] <= until:
            _, _, item = heapq.heappop(opened)
            symbols.remove(item['symbol'])
            equity += item['pnl'] + item['entry_fee']
            free += item['notional'] + item['pnl'] + item['entry_fee']
            completed.append(item)
            peak = max(peak, equity)
            drawdown = max(drawdown, (peak-equity)/peak*100)
            curve.append({'時間':item['exit_time'],'已實現權益':equity})
    for row in trades:
        settle(row['_start'])
        budget = equity * allocation_pct / 100
        if equity <= 0 or budget <= 0 or free + 1e-8 < budget or len(opened) >= max_positions or row['symbol'] in symbols:
            skipped += 1
            continue
        notional = budget / (1 + fee_pct/100)
        entry_fee = notional * fee_pct/100
        direction = 1 if row['side']=='LONG' else -1
        drag = (slippage_pct + spread_pct/2)/100
        entry_fill = row['entry'] * (1+direction*drag)
        exit_fill = row['exit'] * (1-direction*drag)
        quantity = notional/entry_fill
        gross = direction*quantity*(exit_fill-entry_fill)
        fee = quantity*(entry_fill+exit_fill)*fee_pct/100
        hours = (row['_end']-row['_start'])/3600
        funding = direction*notional*funding_pct_8h/100*hours/8
        item = {k:v for k,v in row.items() if not k.startswith('_')}
        item.update(notional=notional, entry_fill=entry_fill, exit_fill=exit_fill,
                    fee=fee, entry_fee=entry_fee, funding=funding, pnl=gross-fee-funding)
        free -= budget
        equity -= entry_fee
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak-equity)/peak*100)
        curve.append({"時間": row["entry_time"], "已實現權益": equity})
        symbols.add(row['symbol'])
        heapq.heappush(opened,(row['_end'],sequence,item))
        sequence += 1
    settle(float('inf'))
    gains = sum(max(t['pnl'],0) for t in completed)
    losses = -sum(min(t['pnl'],0) for t in completed)
    return {'initial':initial,'final':equity,'net_pct':(equity/initial-1)*100,
            'realized_drawdown_pct':drawdown,'trades':completed,'curve':curve,
            'skipped':skipped,'excluded':excluded,'profit_factor':gains/losses if losses else None,
            'assumptions':dict(initial=initial,allocation_pct=allocation_pct,max_positions=max_positions,
                fee_pct=fee_pct,slippage_pct=slippage_pct,spread_pct=spread_pct,funding_pct_8h=funding_pct_8h)}

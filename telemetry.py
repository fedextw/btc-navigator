"""Read-only, bounded telemetry aggregation shared by the terminal views."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import time
from zoneinfo import ZoneInfo

from runtime_config import STATE_ROOT

TAIPEI = ZoneInfo('Asia/Taipei')


def training_activity(root=STATE_ROOT, interval='1h', mode='live', now=None):
    now = now or datetime.now(TAIPEI)
    start = now.astimezone(TAIPEI).replace(hour=0, minute=0, second=0, microsecond=0)
    result = {'today': 0, 'today_passed': 0, 'recent': [], 'days': []}
    path = Path(root) / 'research.sqlite3'
    if not path.exists():
        return result
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5) as db:
        for day in range(6, -1, -1):
            begin = start - timedelta(days=day)
            # Parse the stored ISO timestamps to compare actual instants (UTC vs Taipei).
            low, high = begin.timestamp(), (begin + timedelta(days=1)).timestamp()
            rows = db.execute('''SELECT research_pass,observed_at FROM training_runs
                WHERE interval=? AND mode=? AND julianday(observed_at)>=julianday(?,'unixepoch')
                AND julianday(observed_at)<julianday(?,'unixepoch')''', (interval, mode, low, high)).fetchall()
            passed = sum(bool(row[0]) for row in rows)
            result['days'].append({'日期': begin.strftime('%m/%d'), '訓練完成': len(rows), '研究門檻通過': passed})
            if day == 0:
                result['today'], result['today_passed'] = len(rows), passed
        for row in db.execute('''SELECT id,observed_at,symbol,research_pass,report FROM training_runs
                WHERE interval=? AND mode=? ORDER BY observed_at DESC LIMIT 60''', (interval, mode)):
            record = json.loads(row[4])
            result['recent'].append({'模型': row[0], '訓練時間': row[1], '交易對': row[2],
                '研究檢驗': '通過' if row[3] else '未通過',
                '測試交易數': record.get('test_stats', {}).get('trades', 0),
                '測試淨報酬%': record.get('test_stats', {}).get('net_pct', 0),
                '最大回撤%': record.get('test_stats', {}).get('max_drawdown_pct', 0),
                '決策': record.get('promotion', {}).get('decision', '—')})
    return result


def paper_totals(summaries):
    trades = sum(s.get('trades', 0) for s in summaries)
    wins = sum(s.get('wins', 0) for s in summaries)
    total = sum(s.get('sum_net_returns', 0) for s in summaries)
    gains = sum(s.get('gross_profit', 0) for s in summaries)
    losses = sum(s.get('gross_loss', 0) for s in summaries)
    return {'trades': trades, 'win_rate': wins / trades * 100 if trades else None,
            'average_pct': total / trades * 100 if trades else None,
            'pending': sum(s.get('pending', 0) for s in summaries),
            'unresolved': sum(s.get('unresolved', 0) for s in summaries),
            'profit_factor': gains / losses if losses > 0 else None,
            'costs_complete': all('gross_profit' in s for s in summaries) if summaries else False}


def health_checks(status, delivery, ai, settings, now=None):
    now = time.time() if now is None else now
    def recent(value, seconds):
        stamp = value.get('updated_at', 0)
        return isinstance(stamp, (int, float)) and 0 <= now - stamp <= seconds
    scanner_ok = recent(status, 240) and status.get('status') not in ('連線失敗', '已暫停')
    partial = status.get("failed", 0) or status.get("deferred", 0)
    checks = [{'name': '市場掃描', 'state': ('部分異常' if partial else '正常') if scanner_ok else '需檢查',
               'note': f"{status.get('status', '等待啟動')} · 失敗 {status.get('failed', 0)} / 延後 {status.get('deferred', 0)}",
               'ok': scanner_ok and not partial}]
    checks.append({'name': 'Telegram 推播程序',
        'state': '未啟用' if not settings['notifications_enabled'] else '在線' if recent(delivery, 60) and not delivery.get('error') else '需檢查',
        'note': '程序在線不代表手機已收到；請使用設定中心的測試通知。',
        'ok': recent(delivery, 60) and not delivery.get('error') if settings['notifications_enabled'] else None})
    checks.append({'name': '文字 AI 背景程序',
        'state': '未啟用' if not settings['auto_ai_enabled'] else '在線' if recent(ai, 60) and not ai.get('error') else '需檢查',
        'note': str(ai.get('error') or ai.get('status') or '等待程序') + ' · Ollama 實際推論請另行測試。',
        'ok': recent(ai, 60) and not ai.get('error') if settings['auto_ai_enabled'] else None})
    return checks


def journal_rows(root=STATE_ROOT, interval='1h', demo=False):
    """Loaded only on the learning page, never on every market refresh."""
    from learning_lab import load_record
    folder = Path(root) / 'paper'
    result = []
    for path in sorted(folder.glob(f'*-{interval}-{"demo" if demo else "live"}.json')):
        record = load_record(path) or {}
        symbol = path.name.rsplit(f'-{interval}-', 1)[0]
        result.extend({**row, 'symbol': symbol} for row in record.get('rows', []))
    return result

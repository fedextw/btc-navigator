"""Durable signals and notification outbox, shared between worker and website."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from sqlite_support import open_database

from runtime_config import STATE_ROOT


def connect(root=STATE_ROOT):
    Path(root).mkdir(parents=True, exist_ok=True)
    return open_database(Path(root) / "signals.sqlite3", """
      CREATE TABLE IF NOT EXISTS scan_state (name TEXT PRIMARY KEY, payload TEXT);
      CREATE TABLE IF NOT EXISTS scan_cache (
        symbol TEXT, interval TEXT, mode TEXT, payload TEXT, PRIMARY KEY(symbol,interval,mode));
      CREATE TABLE IF NOT EXISTS scan_results (
        symbol TEXT, interval TEXT, mode TEXT, updated_at TEXT, side TEXT, score INTEGER,
        payload TEXT, PRIMARY KEY(symbol,interval,mode));
      CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY, created_at REAL, expires_at REAL, symbol TEXT, interval TEXT,
        side TEXT, mode TEXT, payload TEXT);
      CREATE TABLE IF NOT EXISTS deliveries (
        event_id TEXT, channel TEXT, status TEXT, attempts INTEGER DEFAULT 0,
        next_attempt REAL DEFAULT 0, updated_at REAL, error TEXT, PRIMARY KEY(event_id,channel));
      CREATE TABLE IF NOT EXISTS ai_reports (
        event_id TEXT PRIMARY KEY, day TEXT, status TEXT, text TEXT, error TEXT, created_at REAL);
      CREATE TABLE IF NOT EXISTS paper_metrics (
        symbol TEXT, interval TEXT, mode TEXT, payload TEXT, PRIMARY KEY(symbol,interval,mode));
    """, rows=True)


def set_state(db, name, value):
    db.execute("INSERT OR REPLACE INTO scan_state VALUES (?,?)", (name, json.dumps(value, ensure_ascii=False, allow_nan=False)))
    db.commit()


def get_state(db, name, default=None):
    row = db.execute("SELECT payload FROM scan_state WHERE name=?", (name,)).fetchone()
    return json.loads(row[0]) if row else default


def save_result(db, result):
    db.execute("INSERT OR REPLACE INTO scan_results VALUES (?,?,?,?,?,?,?)",
               (result["symbol"], result["interval"], result["mode"], result["updated_at"], result["side"], result["score"],
                json.dumps(result, ensure_ascii=False, allow_nan=False)))


def record_signal(db, signal, cooldown_minutes=60, now=None):
    now = time.time() if now is None else now
    # Even an accidentally fabricated direction may not turn demo data into a push.
    if signal["mode"] != "live" or signal["side"] not in ("LONG", "SHORT") or signal["expires_at"] <= now:
        return None
    identity = hashlib.sha256(f'{signal["symbol"]}/{signal["interval"]}/{signal["candle_time"]}/{signal["side"]}'.encode()).hexdigest()[:24]
    with db:
        previous = db.execute("SELECT created_at FROM events WHERE symbol=? AND interval=? AND side=? AND mode='live' ORDER BY created_at DESC LIMIT 1",
            (signal["symbol"], signal["interval"], signal["side"])).fetchone()
        if previous and now - previous[0] < cooldown_minutes * 60:
            return None
        cursor = db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)",
            (identity, now, signal["expires_at"], signal["symbol"], signal["interval"], signal["side"], signal["mode"],
             json.dumps(signal, ensure_ascii=False, allow_nan=False)))
    return identity if cursor.rowcount else None


def latest_events(db, limit=50):
    return [dict(row) for row in db.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,))]

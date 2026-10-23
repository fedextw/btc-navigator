"""Opt-in, quota-limited text commentary on already-qualified research events."""
from datetime import datetime
import json
import os
import time
from zoneinfo import ZoneInfo
import pandas as pd

from ai_research import summarize
from collector import connect as research_db
from monitor_settings import load_settings, load_credentials
from runtime_config import STATE_ROOT


def generate_pending(db, root=STATE_ROOT, summarizer=summarize):
    settings = load_settings(root)
    if not settings["auto_ai_enabled"]:
        return "disabled"
    credentials = load_credentials(root) if settings["ai_provider"] == "openai" else {}
    key = (os.environ.get("AI_API_KEY") or credentials.get("ai_api_key")) if settings["ai_provider"] == "openai" else None
    if settings["ai_provider"] == "openai" and not key:
        return "missing_ai_key"
    day = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    db.execute("BEGIN IMMEDIATE")
    used = db.execute("SELECT COUNT(*) FROM ai_reports WHERE day=?", (day,)).fetchone()[0]
    if used >= settings["ai_daily_limit"]:
        db.rollback()
        return "daily_limit"
    event = db.execute("""SELECT e.* FROM events e LEFT JOIN ai_reports a ON e.id=a.event_id
        WHERE a.event_id IS NULL AND e.mode='live' AND e.expires_at>? AND e.id NOT LIKE '%-ai'
        ORDER BY e.created_at DESC LIMIT 1""", (time.time(),)).fetchone()
    if not event:
        db.rollback()
        return "no_pending_signal"
    db.execute("INSERT INTO ai_reports VALUES (?,?,?,?,?,?)", (event["id"], day, "running", None, None, time.time()))
    db.commit()
    payload = json.loads(event["payload"])
    context, articles = {}, []
    source_db = research_db(root)
    try:
        row = source_db.execute("SELECT payload FROM market_context ORDER BY observed_at DESC LIMIT 1").fetchone()
        context = json.loads(row[0]) if row else {}
        rows = source_db.execute("SELECT title,url,source,published FROM news ORDER BY first_observed_at DESC LIMIT 12").fetchall()
        articles = [{"title": r[0], "url": r[1], "source": r[2], "published": r[3]} for r in rows]
    finally:
        source_db.close()
    # Keep the exact source index shown to the model, so generated [n] citations
    # remain inspectable after feeds change. No credential is part of this record.
    payload["ai_sources"] = articles
    payload["ai_context"] = context
    db.execute("UPDATE events SET payload=? WHERE id=?", (json.dumps(payload, ensure_ascii=False), event["id"]))
    db.commit()
    market = {"symbol": payload["symbol"], "interval": payload["interval"], "mode": "live"}
    result = {"frame": pd.DataFrame([{"close_time": payload["candle_time"]}]),
              "score": payload["score"], "side": payload["side"], "factors": payload["factors"],
              "reasons": ["已通過研究篩選，未經實盤驗證", "新聞只有標題，不是全文"]}
    try:
        text = summarizer(market, result, articles, key, context,
                          provider=settings["ai_provider"], model=settings["ollama_model"])
        db.execute("UPDATE ai_reports SET status='complete',text=? WHERE event_id=?", (text, event["id"]))
        # Only supplement an already successfully delivered primary alert.
        delivered = db.execute("SELECT status FROM deliveries WHERE event_id=? AND channel='telegram'", (event["id"],)).fetchone()
        if settings["notifications_enabled"] and delivered and delivered[0] == "sent" and event["expires_at"] > time.time():
            note = {**payload, "kind": "ai_note", "ai_text": text}
            db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)", (event["id"] + "-ai", time.time(), event["expires_at"],
                event["symbol"], event["interval"], event["side"], "live", json.dumps(note, ensure_ascii=False)))
        db.commit()
        return "complete"
    except Exception as exc:
        db.execute("UPDATE ai_reports SET status='failed',error=? WHERE event_id=?", (type(exc).__name__, event["id"]))
        db.commit()
        return "failed"

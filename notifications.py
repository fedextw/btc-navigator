"""Telegram delivery with a durable claim and no automatic retry of ambiguous sends."""
from datetime import datetime, timezone
import json
import time
import requests

from monitor_settings import effective_credentials, load_settings
from runtime_config import STATE_ROOT


class DeliveryError(Exception):
    def __init__(self, code, retry_after=None, ambiguous=False):
        self.code, self.retry_after, self.ambiguous = code, retry_after, ambiguous
        super().__init__(code)


def send_message(text, credentials, channel="telegram", transport=requests.post):
    if channel != "telegram":
        raise DeliveryError("unsupported_channel")
    token, chat = credentials.get("telegram_token"), credentials.get("telegram_chat")
    if not token or not chat:
        raise DeliveryError("missing_telegram_settings")
    try:
        response = transport(f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True}, timeout=(5, 15))
    except requests.RequestException:
        # A timeout may have occurred after Telegram accepted the request.
        raise DeliveryError("network_result_unknown", ambiguous=True) from None
    try:
        body = response.json()
    except ValueError:
        raise DeliveryError("response_result_unknown", ambiguous=True) from None
    if response.status_code == 429 or body.get("error_code") == 429:
        delay = min(max(int(body.get("parameters", {}).get("retry_after", 60)), 1), 3600)
        raise DeliveryError("telegram_rate_limit", retry_after=delay)
    if not response.ok or not body.get("ok"):
        # Never record response bodies/URLs: a URL embeds the bot token.
        raise DeliveryError(f'telegram_http_{response.status_code}', ambiguous=response.status_code >= 500)
    return str(body.get("result", {}).get("message_id", "accepted"))


def format_signal(signal):
    if signal.get("kind") == "ai_note":
        return f'◈ AI 補充研究｜{signal["symbol"]}｜{signal["interval"]}\n{signal["ai_text"][:3500]}\n生成文字需核對，不更改原訊號價格與條件。'
    direction = "偏多 LONG" if signal["side"] == "LONG" else "偏空 SHORT"
    def price(number):
        return f"{number:,.2f}" if number >= 10 else f"{number:.8f}"
    probability = signal.get("model_probability")
    reason = "；".join(f["evidence"] for f in signal.get("factors", []) if f["score"] != 0)
    lines = [f'◈ 合約研究訊號｜{signal["symbol"]}｜{signal["interval"]}', direction,
        f'參考收盤價：{price(signal["entry"])} USDT', f'偵測時標記價格：{price(signal["mark_price"])}',
        f'假設停損：{price(signal["stop"])}', '研究目標：' + ' / '.join(price(v) for v in signal["targets"]),
        f'規則分數：{signal["score"]:+d}；模型：{signal.get("model_id", "—")}',
        f'模型上漲輸出：{probability:.1%}（不是勝率）' if probability is not None else '模型機率：無資料',
        '理由：' + reason[:650], f'已收盤 K 線（UTC）：{signal["candle_time"]}',
        '有效期限（UTC）：' + datetime.fromtimestamp(signal["expires_at"], timezone.utc).isoformat(),
        '這是待獨立核對的研究訊號，非成交指令或獲利保證；不會替你下單。']
    news = signal.get("news", [])
    if news:
        lines.append('背景新聞（僅標題，未驗證與走勢的因果）：')
        lines.extend(f'{item["source"]}：{item["title"][:100]}\n{item["url"]}' for item in news[:2])
    return '\n'.join(lines)


def dispatch(db, root=STATE_ROOT, now=None, sender=send_message):
    now = time.time() if now is None else now
    settings = load_settings(root)
    if not settings["notifications_enabled"] or settings["channel"] != "telegram":
        return {"sent": 0, "failed": 0}
    credentials = effective_credentials(root)
    if not credentials.get("telegram_token") or not credentials.get("telegram_chat"):
        return {"sent": 0, "failed": 0, "error": "missing_telegram_settings"}
    # A prior process may have died after transmitting but before saving success.
    # Keep it unknown instead of blindly sending again after restart.
    db.execute("UPDATE deliveries SET status='unknown',error='interrupted_send' WHERE status='sending' AND updated_at < ?", (now - 60,))
    db.commit()
    rows = db.execute("""SELECT e.* FROM events e LEFT JOIN deliveries d
        ON e.id=d.event_id AND d.channel='telegram'
        WHERE e.mode='live' AND e.expires_at > ? AND (d.event_id IS NULL OR
          (d.status='retry' AND d.next_attempt<=? AND d.attempts<5)) ORDER BY e.created_at LIMIT 20""", (now, now)).fetchall()
    result = {"sent": 0, "failed": 0}
    for event in rows:
        # Claim under a write lock so two dispatchers cannot send the same event.
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT status,next_attempt,attempts FROM deliveries WHERE event_id=? AND channel='telegram'", (event["id"],)).fetchone()
        if previous and (previous[0] != "retry" or previous[1] > now or previous[2] >= 5):
            db.rollback()
            continue
        attempts = (previous[2] if previous else 0) + 1
        db.execute("INSERT OR REPLACE INTO deliveries VALUES (?,?,?,?,?,?,?)",
            (event["id"], "telegram", "sending", attempts, 0, now, None))
        db.commit()
        try:
            sender(format_signal(json.loads(event["payload"])), credentials)
            status, error, next_attempt = "sent", None, 0
            result["sent"] += 1
        except DeliveryError as exc:
            status = "unknown" if exc.ambiguous else "retry" if exc.retry_after is not None else "failed"
            error, next_attempt = exc.code, now + (exc.retry_after or 0)
            result["failed"] += 1
        except Exception:
            status, error, next_attempt = "unknown", "unexpected_result_unknown", 0
            result["failed"] += 1
        db.execute("UPDATE deliveries SET status=?,error=?,next_attempt=?,updated_at=? WHERE event_id=? AND channel='telegram'",
            (status, error, next_attempt, time.time(), event["id"]))
        db.commit()
    return result

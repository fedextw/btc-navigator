"""Read only updates explicitly requested in the local settings screen."""
import re
import requests


def recent_chats(token, get=requests.get):
    if not re.fullmatch(r"[0-9]{5,16}:[A-Za-z0-9_-]{20,100}", token or ""):
        raise ValueError("請先輸入正確的 Telegram Bot Token")
    try:
        response = get(f"https://api.telegram.org/bot{token}/getUpdates", params={"timeout": 0, "limit": 30}, timeout=(5, 10))
        body = response.json()
        if not response.ok or not body.get("ok"):
            raise ValueError("Telegram 未接受請求。請檢查 Token，或確認機器人未被其他 webhook 程式占用。")
        chats = {}
        for item in body.get("result", []):
            message = item.get("message") or item.get("channel_post") or {}
            chat = message.get("chat", {})
            if "id" in chat:
                chats[chat["id"]] = {"id": str(chat["id"]), "name": chat.get("title") or chat.get("first_name") or chat.get("username") or "Telegram 對話"}
        return list(chats.values())
    except requests.RequestException:
        raise ValueError("無法連線 Telegram，請檢查網路。") from None

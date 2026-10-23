"""Monitor preferences plus local secrets; Windows secrets use per-user DPAPI."""
import base64
import ctypes
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

from learning_lab import save_record, load_record
from runtime_config import STATE_ROOT

DEFAULTS = {"enabled": True, "interval": "1h", "poll_seconds": 60,
            "min_volume_usdt": 5_000_000, "training_per_cycle": 3,
            "notifications_enabled": False, "channel": "site", "cooldown_minutes": 60,
            "auto_ai_enabled": False, "ai_daily_limit": 5,
            "ai_provider": "ollama", "ollama_model": "qwen3:8b"}


def load_settings(root=STATE_ROOT):
    return {**DEFAULTS, **(load_record(Path(root) / "monitor-settings.json") or {})}


def save_settings(values, root=STATE_ROOT):
    data = {**load_settings(root), **values}
    if data["interval"] not in ("15m", "1h", "4h") or data["channel"] not in ("site", "telegram", "discord"):
        raise ValueError("週期或通知管道不正確")
    if not 30 <= data["poll_seconds"] <= 300 or not 1 <= data["training_per_cycle"] <= 10:
        raise ValueError("掃描或訓練參數超出範圍")
    if not 0 <= data["min_volume_usdt"] <= 1e12 or not 0 <= data["cooldown_minutes"] <= 1440:
        raise ValueError("成交額或冷卻時間不正確")
    if not isinstance(data["enabled"], bool) or not isinstance(data["notifications_enabled"], bool):
        raise ValueError("啟用狀態不正確")
    if not 1 <= data["ai_daily_limit"] <= 50 or not isinstance(data["auto_ai_enabled"], bool):
        raise ValueError("AI 自動解讀設定不正確")
    if data["ai_provider"] not in ("ollama", "openai"):
        raise ValueError("AI 供應者不正確")
    if not isinstance(data["ollama_model"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", data["ollama_model"]) or "cloud" in data["ollama_model"].lower():
        raise ValueError("請填本機模型名稱，例如 qwen3:4b；不支援 cloud 模型")
    save_record(Path(root) / "monitor-settings.json", data)
    return data


def _dpapi(data, decrypt=False):
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destination = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(destination)):
        raise OSError("Windows 無法存取本帳戶的加密設定")
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(destination.pbData)


def load_credentials(root=STATE_ROOT):
    record = load_record(Path(root) / "notification-secrets.json")
    if not record:
        return {}
    if record.get("protection") == "windows-dpapi":
        if sys.platform != "win32":
            raise ValueError("這份推播設定由 Windows 帳戶加密，請在新機器重新填入")
        return json.loads(_dpapi(base64.b64decode(record["data"]), decrypt=True))
    return record.get("credentials", {})


def save_credentials(changes, root=STATE_ROOT):
    try:
        existing = load_credentials(root)
    except (OSError, ValueError):
        if not any(changes.values()):
            raise
        existing = {}
    credentials = {**existing, **{k: v.strip() for k, v in changes.items() if v and v.strip()}}
    if credentials.get("telegram_token") and not re.fullmatch(r"[0-9]{5,16}:[A-Za-z0-9_-]{20,100}", credentials["telegram_token"]):
        raise ValueError("Telegram Bot Token 格式不正確")
    if credentials.get("telegram_chat") and not re.fullmatch(r"-?[0-9]{1,20}|@[A-Za-z0-9_]{5,40}", credentials["telegram_chat"]):
        raise ValueError("Telegram Chat ID 格式不正確")
    if credentials.get("discord_webhook"):
        url = urlparse(credentials["discord_webhook"])
        if url.scheme != "https" or url.hostname != "discord.com" or url.port is not None or url.query or url.fragment or url.username or not re.fullmatch(r"/api/webhooks/[0-9]+/[A-Za-z0-9._-]+", url.path):
            raise ValueError("請使用 Discord 官方 https://discord.com/api/webhooks/... 網址")
    if sys.platform == "win32":
        encoded = _dpapi(json.dumps(credentials).encode())
        record = {"protection": "windows-dpapi", "data": base64.b64encode(encoded).decode()}
    else:
        record = {"protection": "local-file", "credentials": credentials}
    path = Path(root) / "notification-secrets.json"
    save_record(path, record)
    os.chmod(path, 0o600)


def effective_credentials(root=STATE_ROOT):
    saved = load_credentials(root)
    return {"telegram_token": os.environ.get("TELEGRAM_BOT_TOKEN") or saved.get("telegram_token", ""),
            "telegram_chat": os.environ.get("TELEGRAM_CHAT_ID") or saved.get("telegram_chat", ""),
            "discord_webhook": os.environ.get("DISCORD_WEBHOOK_URL") or saved.get("discord_webhook", "")}

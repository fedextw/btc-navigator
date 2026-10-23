"""Full-market monitor, automatic-learning status, and Telegram configuration."""
from datetime import datetime
import json
import time
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from monitor_settings import load_settings, save_settings, load_credentials, save_credentials, effective_credentials
from notifications import send_message, DeliveryError
from runtime_config import STATE_ROOT
from signal_store import connect, get_state, latest_events


def discovered_symbols():
    db = connect()
    try:
        return get_state(db, "universe", {}).get("symbols", [])
    finally:
        db.close()


def settings_panel():
    settings = load_settings()
    try:
        credentials = effective_credentials()
        stored = load_credentials()
    except (ValueError, OSError):
        credentials, stored = {}, {}
        st.warning("此機器無法解開原帳戶的設定，請重新填入推播資料。")
    with st.expander("監控、Telegram 與自動 AI 設定", expanded=not settings["notifications_enabled"]):
        st.markdown("**首次設定 Telegram**")
        st.markdown("1. 在 Telegram 找官方 **@BotFather**，用 `/newbot` 建立機器人並取得 Token。\n2. 開啟你的機器人對話並按 **Start**，先傳一則訊息。\n3. 下方填入 Token，按「取得我的 Chat ID」，選擇要接收通知的對話。")
        token_for_lookup = st.text_input("Token（只用於取得 Chat ID）", type="password", key="telegram_lookup_token")
        if st.button("取得我的 Chat ID"):
            from telegram_setup import recent_chats
            try:
                with st.spinner("向 Telegram 讀取你傳給機器人的訊息…"):
                    chats = recent_chats(token_for_lookup or credentials.get("telegram_token", ""))
                st.session_state["telegram_chats"] = chats
                if not chats:
                    st.warning("目前沒有訊息。請先到你的機器人按 Start 並傳一則文字，再按一次。")
            except ValueError as exc:
                st.error(str(exc))
        chats = st.session_state.get("telegram_chats", [])
        if chats:
            choice = st.selectbox("選擇接收對話", chats, format_func=lambda c: f'{c["name"]} · {c["id"]}')
            st.caption("請將選定的 Chat ID 填入下方：" + str(choice["id"]))
        with st.form("monitor-configuration"):
            active = st.checkbox("啟用全市場自動監控與模擬學習", value=settings["enabled"])
            a, b = st.columns(2)
            interval = a.selectbox("全市場訊號週期", ["15m", "1h", "4h"], index=["15m", "1h", "4h"].index(settings["interval"]))
            min_volume = b.number_input("訊號最低 24h 成交額（USDT）", min_value=0.0, max_value=1e12, value=float(settings["min_volume_usdt"]), step=1_000_000.0)
            st.caption("所有交易中的 USDT 永續合約都會掃描；低於此成交額的幣種列在結果中，但不訓練／推播。設為 0 可取消成交額篩選。")
            enabled = st.checkbox("啟用 Telegram 訊號推播", value=settings["notifications_enabled"])
            token = st.text_input("Telegram Bot Token", type="password", help="留空保留已儲存的 Token。")
            chat = st.text_input("Telegram Chat ID", help="私訊為數字，群組通常為負數。留空保留既有設定。")
            st.caption("已儲存 Telegram 設定。" if credentials.get("telegram_token") and credentials.get("telegram_chat") else "尚未完成 Telegram 設定。")
            cooldown = st.number_input("同幣同方向冷卻分鐘", min_value=0, max_value=1440, value=int(settings["cooldown_minutes"]))
            training = st.slider("每輪最多準備／重訓模型數", 1, 10, int(settings["training_per_cycle"]))
            st.markdown("**自動 AI 文字解讀（選用，與本機學習模型分開）**")
            provider = st.selectbox("文字 AI 供應者", ["ollama", "openai"], index=["ollama", "openai"].index(settings["ai_provider"]), format_func=lambda x: "Ollama 本機（免 API 費）" if x == "ollama" else "OpenAI（付費 API）")
            local_model = st.text_input("Ollama 本機模型名稱", value=settings["ollama_model"])
            auto_ai = st.checkbox("啟用 AI 自動解讀合格訊號", value=settings["auto_ai_enabled"])
            st.caption("Ollama 須先安裝並下載模型；只連本機 127.0.0.1:11434，不會自動改用 OpenAI。OpenAI 模式可能產生 API 費用。")
            ai_key = st.text_input("OpenAI API Key（選用）", type="password", help="留空保留已儲存金鑰。背景程序需要保存後才能讀取。")
            quota = st.number_input("每日最多 AI 解讀次數（台北日界）", 1, 50, int(settings["ai_daily_limit"]))
            st.caption("Telegram 主訊號不等待文字模型；若啟用，AI 會另讀指標、新聞標題與市場背景，在網站補上解讀，主訊號已送達時再推播補充。")
            if st.form_submit_button("儲存並套用背景設定", type="primary"):
                try:
                    if enabled and not ((token or token_for_lookup or credentials.get("telegram_token")) and (chat or credentials.get("telegram_chat"))):
                        raise ValueError("請填妥 Telegram Token 與 Chat ID 後再啟用推播")
                    if auto_ai and provider == "openai" and not (ai_key or stored.get("ai_api_key") or __import__("os").environ.get("AI_API_KEY")):
                        raise ValueError("啟用自動文字解讀前，請先設定 OpenAI API Key")
                    save_credentials({"telegram_token": token or token_for_lookup, "telegram_chat": chat, "ai_api_key": ai_key})
                    save_settings({"enabled": active, "interval": interval, "min_volume_usdt": min_volume,
                        "notifications_enabled": enabled, "channel": "telegram" if enabled else "site",
                        "cooldown_minutes": cooldown, "training_per_cycle": training,
                        "auto_ai_enabled": auto_ai, "ai_daily_limit": quota,
                        "ai_provider": provider, "ollama_model": local_model})
                    st.success("設定已保存。背景程序下一輪會套用；推播設定每幾秒讀取一次。")
                except (ValueError, OSError) as exc:
                    st.error(str(exc))
        if st.button("檢查已儲存的 Ollama 連線與模型"):
            from ai_research import check_ollama
            try:
                check_ollama(load_settings()["ollama_model"])
                st.success("Ollama 已連線，指定模型已安裝。可到單幣研究產生摘要測試推論。")
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))
        if st.button("發送 Telegram 測試通知"):
            try:
                send_message("◈ BTC Navigator 測試通知\n手機推播已連通。這是連線測試，不是交易訊號。", effective_credentials())
                st.success("Telegram 已接受測試訊息，請查看手機。")
            except DeliveryError as exc:
                st.error("測試通知未確認送達：" + exc.code + "。請檢查 Token、Chat ID，以及是否已對機器人按 Start。")
        st.caption("金鑰只存於本機 .local-state，Windows 使用目前登入帳戶的 DPAPI 加密。不要分享該資料夾。關閉瀏覽器後仍會監控；關閉啟動視窗或電腦休眠會停止。")


@st.fragment(run_every=10)
def status_panel():
    db = connect()
    try:
        status = get_state(db, "status", {})
        delivery = get_state(db, "delivery_status", {})
        settings = load_settings()
        if not status:
            st.info("正在等待全市場背景程序。請使用新版 START.bat 啟動；只開 Streamlit 不會啟動掃描器。")
        else:
            age = time.time() - status.get("updated_at", 0)
            if age > 240:
                st.warning("背景心跳已超過 4 分鐘，請確認啟動視窗仍開著，並檢查 .local-state/scanner.log。")
            if status.get("mode") == "demo":
                st.warning("示範模式只掃描 6 個合成交易對，不代表 Binance 全市場；不會產生外部交易訊號推播。")
            a, b, c, d = st.columns(4)
            a.metric("交易所合約數", status.get("universe", 0))
            b.metric("本輪已分析", status.get("analyzed", 0))
            c.metric("通過研究門檻的模型", status.get("models_ready", 0))
            d.metric("本輪資料失敗／延後", f'{status.get("failed", 0)} / {status.get("deferred", 0)}')
            st.caption(f'狀態：{status.get("status")} · {status.get("interval", "1h")} · 本輪 {status.get("duration_seconds", 0)} 秒 · 心跳 {int(age)} 秒前')
            for error in status.get("errors", [])[:8]:
                st.caption(error)
        if delivery.get("error"):
            st.warning("推播程序狀態：" + delivery["error"])
        auto_ai = get_state(db, "auto_ai_status", {})
        if settings["auto_ai_enabled"]:
            st.caption("自動文字 AI 狀態：" + str(auto_ai.get("status") or auto_ai.get("error") or "等待背景程序"))
        interval = settings["interval"]
        mode = status.get("mode", "live")
        active = set(get_state(db, "universe", {}).get("symbols", []))
        rows = [json.loads(r[0]) for r in db.execute("SELECT payload FROM scan_results WHERE interval=? AND mode=? ORDER BY ABS(score) DESC,symbol", (interval, mode))]
        if mode == "live" and active:
            rows = [row for row in rows if row["symbol"] in active]
        filter_text = st.text_input("搜尋全市場交易對", placeholder="例如 ETH、SOL、1000PEPE…")
        only_setups = st.checkbox("只顯示規則偏多／偏空的候選", value=False)
        selected = [r for r in rows if filter_text.upper() in r["symbol"] and (not only_setups or r["rule_side"] != "WAIT")]
        if selected:
            table = pd.DataFrame([{"交易對": r["symbol"], "綜合方向": r["side"], "規則": r["rule_side"],
                "分數": r["score"], "模型": r.get("model_side") or "尚未準備", "狀態": r["status"],
                "標記價格": r.get("mark_price"), "24h成交額": r.get("volume_24h"),
                "觀望原因": "、".join(r.get("reasons", [])), "更新UTC": r["updated_at"]} for r in selected])
            st.dataframe(table, hide_index=True, width="stretch", height=380)
            inspect = st.selectbox("選擇幣種深入研究", [r["symbol"] for r in selected], key="scanner_inspect_symbol")
            if st.button("開啟單幣分析"):
                st.session_state["pending_symbol"] = inspect
                st.session_state["pending_workspace"] = "單幣研究"
                st.rerun()
        else:
            st.caption("尚無符合條件的掃描結果。首次需先取得全市場行情並排隊準備模型。")
        st.markdown("### 訊號中心與發送紀錄")
        events = latest_events(db, 50)
        if not events:
            st.info("目前沒有符合全部條件的研究訊號。模型未準備好、未通過檢驗或規則不一致時，系統會保持觀望。")
        for event in events[:20]:
            payload = json.loads(event["payload"])
            delivered = db.execute("SELECT status,attempts,error FROM deliveries WHERE event_id=? AND channel='telegram'", (event["id"],)).fetchone()
            state = delivered[0] if delivered else "待推播" if settings["notifications_enabled"] else "僅網站"
            expired = event["expires_at"] < time.time()
            stamp = datetime.fromtimestamp(event["created_at"], ZoneInfo("Asia/Taipei")).strftime("%m/%d %H:%M:%S")
            heading = f'{payload["symbol"]} · {payload["side"]} · {stamp} · {"已過期" if expired else "研究訊號"} · {state}'
            with st.expander(heading):
                if payload.get("kind") == "ai_note":
                    st.markdown(payload["ai_text"])
                else:
                    st.write(f'參考價 {payload["entry"]:g} ／ 假設停損 {payload["stop"]:g}')
                    st.write("研究目標：" + " / ".join(f"{v:g}" for v in payload["targets"]))
                    st.caption("模型上漲輸出不等同勝率；價格是訊號偵測時的研究價位，不是成交回報。")
                    for factor in payload.get("factors", []):
                        st.write(f'{factor["name"]}：{factor["evidence"]}')
                    ai = db.execute("SELECT status,text,error FROM ai_reports WHERE event_id=?", (event["id"],)).fetchone()
                    if ai:
                        st.markdown(ai[1]) if ai[0] == "complete" else st.caption("AI 解讀：" + ai[0])
                if delivered and delivered[2]:
                    st.caption("發送狀態：" + delivered[2] + "。unknown 表示結果不明，系統不會自動重送以免重複。")
                for index, source in enumerate(payload.get("ai_sources", []), 1):
                    st.caption(f'[{index}] {source["source"]}：{source["title"]}')
                    st.link_button("新聞原始來源", source["url"], key=f'ai-ref-{event["id"]}-{index}')
        summaries = [json.loads(r["payload"]) for r in db.execute("SELECT symbol,payload FROM paper_metrics WHERE interval=? AND mode=?", (interval,mode))
                     if mode == "demo" or not active or r["symbol"] in active]
        trades = sum(s.get("trades", 0) for s in summaries)
        wins = sum(s.get("wins", 0) for s in summaries)
        net_sum = sum(s.get("sum_net_returns", 0) for s in summaries)
        pending = sum(s.get("pending", 0) for s in summaries)
        unresolved = sum(s.get("unresolved", 0) for s in summaries)
        st.markdown("### 持續模擬與學習紀錄")
        a, b, c, d = st.columns(4)
        a.metric("已結算紙上交易", trades)
        b.metric("紙上交易勝率", f'{wins / trades * 100:.1f}%' if trades else "尚無樣本")
        c.metric("等待未來行情／無法還原", f"{pending} / {unresolved}")
        d.metric("平均每筆淨報酬 · 1× 名目", f'{net_sum / trades * 100:+.3f}%' if trades else "尚無樣本")
        st.caption("統計涵蓋目前掃描範圍的模型。不同幣種可能同時持倉，不能將逐筆報酬直接相乘當成投資組合獲利。各幣種的模型、回測與交易明細可在單幣研究查看。")
        evolution = [json.loads(row[0]) for row in db.execute("SELECT payload FROM scan_state WHERE name LIKE 'evolution/%'")]
        if evolution:
            with st.expander("模型自我更新與晉升紀錄"):
                st.dataframe(pd.DataFrame([{"決策": a["decision"], "原因": a["reason"],
                    "現行模型": a.get("incumbent_id", "首次"), "候選模型": a.get("candidate_id", "—")} for a in evolution]), hide_index=True)
    finally:
        db.close()


def scanner_page():
    st.markdown("# 全市場訊號終端")
    st.caption("動態追蹤 Binance 所有交易中、USDT 計價且以 USDT 保證金的永續合約。自動研究、模擬學習、條件篩選與 Telegram 推播。")
    st.info("1h 訊號在 K 線收盤後判斷，預設每 60 秒啟動一輪；全市場耗時與速率限制會增加延遲。首次模型需排隊準備，不會立即對所有幣種產生合格訊號。")
    settings_panel()
    status_panel()

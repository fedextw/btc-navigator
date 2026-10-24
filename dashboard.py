"""Traditional Chinese derivatives research dashboard."""
import html
import json
import os
import time
from datetime import datetime
from pathlib import Path
import sqlite3

import altair as alt
import pandas as pd
import streamlit as st

from analysis_engine import analyze, position_size
from market_data import SYMBOLS, load_market, load_news
from ai_research import summarize
from lab_ui import learning_tab
from runtime_config import STATE_ROOT
from context_data import load_context
from decision_engine import consensus
from learning_lab import model_path, load_record
from scanner_ui import scanner_page, discovered_symbols, settings_panel


from terminal_theme import STYLE
from terminal_ui import hero, learning_page, health_page


def esc(value):
    return html.escape(str(value), quote=True)


def price(value):
    if value is None:
        return "—"
    return f"{value:,.2f}" if value >= 10 else f"{value:,.5f}"


def metric(label, value, foot, color=""):
    st.markdown(f'<div class="card"><div class="metric-label">{esc(label)}</div>'
                f'<div class="metric-value {color}">{esc(value)}</div>'
                f'<div class="metric-foot">{esc(foot)}</div></div>', unsafe_allow_html=True)


def monitor_status(symbol, interval, mode):
    signals = STATE_ROOT / "signals.sqlite3"
    if signals.exists():
        from signal_store import connect as signals_db, get_state
        db = signals_db()
        try:
            scanner = get_state(db, "status", {})
            if scanner:
                age = time.time() - scanner.get("updated_at", 0)
                return f'全市場背景：{scanner["status"]} · {scanner.get("interval", "1h")} · {int(age)} 秒前；本頁幣種選擇不限制背景掃描。'
        finally:
            db.close()
    path = STATE_ROOT / "research.sqlite3"
    if not path.exists():
        return "背景監控尚未啟動；目前僅網頁更新。"
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            row = db.execute("SELECT updated_at,status,detail FROM heartbeat WHERE name=?",
                (f'{symbol}/{interval}/{"demo" if mode == "demo" else "live"}',)).fetchone()
        if not row:
            return "此交易對／週期尚無背景監控；切換網頁不會改變背景程序的監控標的。"
        age = (pd.Timestamp.now(tz="UTC") - pd.Timestamp(row[0])).total_seconds()
        return f'背景監控 · {row[1] if age < 180 else "心跳逾時"} · {int(age)} 秒前 · {row[2]}'
    except sqlite3.Error:
        return "背景資料庫尚在初始化。"


@st.cache_data(ttl=60, show_spinner=False)
def cached_market(symbol, interval, mode):
    return load_market(symbol, interval, mode)


@st.cache_data(ttl=300, show_spinner=False)
def cached_news():
    return load_news()


@st.cache_data(ttl=900, show_spinner=False)
def cached_context():
    return load_context()


def candle_chart(result, show_zones=True):
    frame = result["frame"].tail(150).copy()
    base = alt.Chart(frame).encode(x=alt.X("time:T", title=None, axis=alt.Axis(format="%m/%d %H:%M", labelColor="#8292ac", grid=False)))
    colors = alt.condition("datum.close >= datum.open", alt.value("#35d9b2"), alt.value("#f5758c"))
    wick = base.mark_rule().encode(y=alt.Y("low:Q", title="USDT", scale=alt.Scale(zero=False)), y2="high:Q", color=colors)
    body = base.mark_bar(size=4).encode(y=alt.Y("open:Q", scale=alt.Scale(zero=False)), y2="close:Q", color=colors,
        tooltip=[alt.Tooltip("time:T", title="K 線時間（UTC）"), "open:Q", "high:Q", "low:Q", "close:Q", "volume:Q"])
    lines = []
    for column, color in (("ema20", "#f4c879"), ("ema50", "#7d9cff"), ("ema200", "#b08be9")):
        lines.append(base.mark_line(strokeWidth=1.3, color=color).encode(y=alt.Y(f"{column}:Q", scale=alt.Scale(zero=False))))
    layers = [wick, body] + lines
    if show_zones:
        structures = result["structure"]
        levels = pd.DataFrame({"level": [structures["high"], structures["low"]], "name": ["20 根區間高", "20 根區間低"]})
        layers.append(alt.Chart(levels).mark_rule(strokeDash=[5, 5], opacity=.45, color="#92a5c0").encode(
            y="level:Q", tooltip=["name:N", "level:Q"]))
        for gap in structures["gaps"]:
            zone = pd.DataFrame([{"start": gap["time"], "end": frame.iloc[-1].time,
                                  "low": gap["low"], "high": gap["high"], "name": gap["kind"]}])
            layers.append(alt.Chart(zone).mark_rect(opacity=.12, color="#35d9b2" if "Bullish" in gap["kind"] else "#f5758c").encode(
                x="start:T", x2="end:T", y="low:Q", y2="high:Q", tooltip=["name:N", "low:Q", "high:Q"]))
    chart = alt.layer(*layers).properties(height=420, width="container",
        autosize=alt.AutoSizeParams(type="fit", contains="padding"))
    return chart.configure_view(stroke=None).configure(
        background="#101927", axis=alt.Axis(gridColor="#202c40", domainColor="#26344c", labelColor="#8192ad", titleColor="#8192ad"))


def signal_panel(market, result):
    decision = result.get("decision", {"side": "WAIT", "gates": {}})
    side = decision["side"]
    label = {"LONG": "偏多 · LONG", "SHORT": "偏空 · SHORT", "WAIT": "觀望 · WAIT"}[side]
    tone = "up" if side == "LONG" else "down" if side == "SHORT" else ""
    demo = market["mode"] == "demo"
    st.markdown(f'<div class="card"><div class="signal-top"><span class="eyebrow">CONFLUENCE ENGINE</span>'
                f'<span class="tag {"demo" if demo else "live"}">{"模擬評估" if demo else "規則評估"}</span></div>'
                f'<div class="signal-title {tone}">{label}</div><div class="subtle">研究共識 · 規則方向 {result["side"]}<br>規則分數 {result["score"]:+d} / ±8 · 非預測勝率</div>'
                '<div class="rule"></div><div class="subtle">僅使用已收盤 K 線。條件未一致時維持觀望；'
                '訊號以每根 K 線收盤重新計算，可能與盤中價格不同。</div></div>', unsafe_allow_html=True)
    for reason in result["reasons"]:
        st.caption("• " + reason)
    with st.expander("AI 與規則共識檢查"):
        for check, passed in decision["gates"].items():
            st.caption(("✓ " if passed else "○ ") + check)
        st.caption("需全部條件成立才顯示研究方向。即使一致，也不代表訊號具有已驗證的實盤勝率。")
    if result["stop"] is not None and side != "WAIT":
        st.markdown('<div class="section-title">研究價位' + (' · 模擬' if demo else '') + '</div>', unsafe_allow_html=True)
        st.metric("參考進場（最後收盤價）", price(result["entry"]))
        one, two = st.columns(2)
        one.metric("停損 · 1.8 ATR", price(result["stop"]))
        two.metric("目標 · 2R", price(result["targets"][1]))
        st.caption("另列 1.5R / 3R 目標：" + " / ".join(price(result["targets"][i]) for i in (0, 2)))
    else:
        st.info("觀望期間不產生進出場價位。可在風險試算中自行設定假設價格。")


def overview(market, result):
    left, right = st.columns([2.4, 1], gap="large")
    with left:
        st.markdown('<div class="section-title">價格與市場結構</div>', unsafe_allow_html=True)
        st.caption("EMA 20 金色 · EMA 50 藍色 · EMA 200 紫色 · 虛線為前 20 根區間 · 陰影為尚未完全回補的 FVG")
        st.altair_chart(candle_chart(result), width="stretch")
        st.caption("圖表時間使用 UTC；K 線不包含尚未收盤的當根。滑鼠移至 K 線可檢視 OHLC。")
    with right:
        signal_panel(market, result)
    st.markdown('<div class="section-title">為什麼得到這個判斷？</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for index, factor in enumerate(result["factors"]):
        with cols[index % 2]:
            value = factor["score"]
            st.markdown(f'<div class="card factor"><div>{esc(factor["name"])}<small>{esc(factor["evidence"])}</small></div>'
                        f'<strong class="{"up" if value > 0 else "down" if value < 0 else ""}">{value:+d}</strong></div>', unsafe_allow_html=True)


def structure_tab(result):
    structure = result["structure"]
    a, b, c = st.columns(3)
    with a:
        metric("市場結構 · BOS", structure["bos"], "收盤突破前 20 根高低點的簡化定義")
    with b:
        metric("流動性事件", "掃單" if "未偵測" not in structure["sweep"] else "無事件", structure["sweep"])
    with c:
        metric("Dealing range", structure["zone"].split()[0], "相對前 20 根區間中點，非估值模型")
    st.altair_chart(candle_chart(result), width="stretch")
    st.markdown("#### FVG · 公允價值缺口")
    if structure["gaps"]:
        gaps = pd.DataFrame(structure["gaps"])
        gaps.columns = ["方向", "下界", "上界", "形成時間（UTC）"]
        st.dataframe(gaps, hide_index=True, width="stretch")
    else:
        st.info("最近 60 根 K 線沒有尚未完全回補的三根 K 線缺口。")
    st.caption("SMC／ICT 為價格行為解讀框架。本版實作區間突破、掃單、溢價／折價與 FVG 啟發式；尚未實作完整訂單塊、CHOCH 或交易時段模型。掃單不代表已證實機構操盤。")


def flow_tab(market):
    st.markdown("### 資金與成交壓力")
    st.caption("用資金費率、未平倉量與主動買賣成交觀察市場。這些數據無法直接識別機構，也不等同鏈上淨流入。")
    frame = market["candles"].tail(100).copy()
    if "taker_buy_quote" not in frame:
        st.info("此資料來源沒有主動買賣成交額。")
        return
    frame["delta"] = frame.taker_buy_quote * 2 - frame.quote_volume
    frame["cvd"] = frame.delta.cumsum()
    a, b, c = st.columns(3)
    total = frame.quote_volume.tail(20).sum()
    a.metric("近 20 根主動買入比例", f'{frame.taker_buy_quote.tail(20).sum() / total * 100:.1f}%' if total > 0 else "無成交")
    b.metric("近 20 根主動買賣差額", f'{frame.delta.tail(20).sum() / 1e6:+.2f}M U')
    c.metric("當期費率", f'{market["funding"]:+.4f}%' if market["funding"] is not None else "不可用")
    base = alt.Chart(frame).encode(x=alt.X("time:T", title="UTC"))
    bars = base.mark_bar().encode(y=alt.Y("delta:Q", title="主動買入 − 賣出（USDT）"),
        color=alt.condition("datum.delta >= 0", alt.value("#38e5bc"), alt.value("#f5758c")), tooltip=["time:T", "delta:Q"])
    line = base.mark_line(color="#7d9cff").encode(y=alt.Y("cvd:Q", title="視窗累計差額（USDT）"), tooltip=["time:T", "cvd:Q"])
    st.altair_chart(alt.vconcat(bars.properties(height=180), line.properties(height=180)).configure_view(stroke=None), width="stretch")
    st.caption("累計成交差額從目前視窗第一根起算，視窗移動時起點也會改變。每筆成交均有買方與賣方；此圖按主動成交方向分類，不代表資金憑空流入或流出。")
    db_path = STATE_ROOT / "research.sqlite3"
    if db_path.exists():
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
            history = pd.read_sql_query("SELECT observed_at,oi_usd,funding FROM snapshots WHERE symbol=? AND interval=? AND mode=? ORDER BY id DESC LIMIT 500", db,
                params=(market["symbol"], market["interval"], market["mode"]))
        if len(history) > 1:
            history["observed_at"] = pd.to_datetime(history.observed_at, utc=True)
            history = history.sort_values("observed_at")
            st.markdown("#### 背景程序累積的 OI 快照")
            st.line_chart(history.set_index("observed_at")[["oi_usd"]], width="stretch")
        else:
            st.caption("背景快照尚不足兩筆；持續監控後即可顯示 OI 變化。")


def risk_tab(market, result):
    st.markdown("### 先決定能承擔的損失，再決定部位")
    st.caption("USDT 線性合約試算；估算含進出場手續費，不含滑價、資金費、強平與跳空損失。")
    left, right = st.columns([1, 1], gap="large")
    with left:
        with st.form("risk-form"):
            equity = st.number_input("帳戶權益（USDT）", min_value=10.0, value=1000.0, step=100.0)
            risk = st.slider("單筆風險上限（%）", 0.1, 5.0, 1.0, 0.1)
            leverage = st.slider("名目槓桿", 1, 50, 3)
            entry = st.number_input("假設進場價", min_value=0.000001, value=float(result["entry"]), format="%.6f")
            default_stop = result["stop"] or result["entry"] - result["distance"]
            stop = st.number_input("假設停損價", min_value=0.000001, value=max(float(default_stop), 0.000001), format="%.6f")
            fee = st.number_input("單邊手續費（%）", min_value=0.0, max_value=1.0, value=0.05, step=0.01)
            submit = st.form_submit_button("計算部位", type="primary", width="stretch")
    with right:
        if market["mode"] == "demo":
            st.warning("目前是示範行情；預填價位不能用於實盤。")
        if submit:
            try:
                sizing = position_size(equity, risk, entry, stop, leverage, fee)
                st.metric("預計停損損失（含估計雙邊費用）", f'{sizing["budget"]:,.2f} USDT')
                st.metric("標的數量", f'{sizing["quantity"]:,.6f} {market["symbol"].removesuffix("USDT")}')
                a, b = st.columns(2)
                a.metric("名目價值", f'{sizing["notional"]:,.2f} U')
                b.metric("初始保證金估算", f'{sizing["margin"]:,.2f} U')
                if sizing["exceeds_equity"]:
                    st.error("估計保證金超過帳戶權益，無法以此設定建立部位。請調整部位與風險。")
                st.caption("增加槓桿不會降低相同部位的停損損失，且會縮短與強平價的距離。本試算未驗證停損是否早於強平。")
            except ValueError as exc:
                st.error(str(exc))
        else:
            st.markdown('<div class="card"><div class="eyebrow">RISK FIRST</div><h3>保留下一次交易的機會</h3>'
                        '<div class="subtle">預設風險為權益的 1%。請依流動性與波動自行調整；停損單不保證依指定價格成交。'
                        '<br><br>本頁計算假設部位，沒有連接交易所帳戶，也不會送出訂單。</div></div>', unsafe_allow_html=True)


def news_tab(market, result, demo):
    st.markdown("### 全球加密新聞 · 來源可追溯")
    st.caption("彙整 CoinDesk、Cointelegraph、Decrypt 公開 RSS；每 5 分鐘更新快取。這是多來源新聞彙整，尚未涵蓋全球所有資訊。")
    if demo:
        st.info("示範模式不發出外部新聞請求；切換即時或自動模式可嘗試載入。")
        articles, errors = [], []
        context = {"data": {}, "errors": {}}
    else:
        with st.spinner("收集公開新聞來源…"):
            articles, errors = cached_news()
            context = cached_context()
    st.markdown("#### 全球市場脈絡")
    context_columns = st.columns(2)
    context_labels = {"market_cap_usd": "全球市值（USD）", "volume_24h_usd": "24h 成交量（USD）",
                      "btc_dominance_pct": "BTC 市佔（%）", "market_cap_change_24h_pct": "市值 24h 變化（%）",
                      "stablecoin_supply_usd": "穩定幣流通供給（USD）", "tvl_usd": "DeFi TVL（USD）",
                      "change_7_samples_pct": "近 7 個樣本間隔變化（%）", "fear_greed": "恐懼貪婪指數（0–100）",
                      "classification": "情緒分類"}
    for index, (source, values) in enumerate(context["data"].items()):
        with context_columns[index % 2]:
            st.markdown(f"**{source}**")
            if values.get("stale"):
                st.warning("此來源資料超過 3 天，僅供歷史背景。")
            for key, label in context_labels.items():
                if key in values:
                    st.write(f'{label}：{values[key]:,.2f}' if isinstance(values[key], (int, float)) else f'{label}：{values[key]}')
            st.caption("來源時間（UTC）：" + values["as_of"])
            st.link_button("公開資料來源", values["source_url"], key=f"context-{index}")
    if context["errors"]:
        st.caption("市場背景來源不可用：" + "、".join(context["errors"]))
    st.caption("穩定幣供給變化不是交易所淨流入；TVL 受資產價格影響，也不是純資金流量。上述背景不會回填歷史訓練或直接變成買賣權重。")
    if errors:
        st.warning("以下來源暫時無法讀取：" + "、".join(errors) + "。不會以虛構新聞補位。")
    filter_text = st.text_input("篩選新聞標題", placeholder="Bitcoin、ETF、Ethereum、Fed…")
    selected = [a for a in articles if filter_text.lower() in a["title"].lower()]
    if not selected:
        st.caption("目前沒有符合條件的新聞。")
    for index, article in enumerate(selected[:18]):
        st.markdown(f'<div class="card"><span class="tag">{esc(article["source"])}</span>'
                    f'<div style="margin-top:12px"><a class="news-title" href="{esc(article["url"])}" target="_blank" rel="noopener noreferrer">{esc(article["title"])}</a></div>'
                    f'<div class="news-meta">{esc(article["published"])}</div></div>', unsafe_allow_html=True)
    st.markdown("### AI 研究助理")
    st.caption("可選：以 Ollama 本機模型或 OpenAI 解讀指標、新聞標題與背景。供應者在全市場設定選擇；本機模式不傳送至 OpenAI。AI 不會讀取新聞全文或替你下單。")
    from monitor_settings import load_settings, load_credentials
    ai_settings = load_settings()
    try:
        saved_key = load_credentials().get("ai_api_key") if ai_settings["ai_provider"] == "openai" else None
    except (ValueError, OSError):
        saved_key = None
    ai_key = st.session_state.get("ai_session_key") or saved_key
    available = ai_settings["ai_provider"] == "ollama" or bool(os.environ.get("AI_API_KEY") or ai_key)
    st.caption("目前文字模型：" + ai_settings["ai_provider"] + (" / " + ai_settings["ollama_model"] if ai_settings["ai_provider"] == "ollama" else ""))
    if not available:
        st.info("尚未設定 AI_API_KEY。目前使用透明的規則評分，不會假稱為 AI 預測。可在環境設定安全加入金鑰；不要在聊天中提供。")
    if st.button("產生本次 AI 研究摘要", disabled=not available, type="primary"):
        try:
            with st.spinner("AI 正在解讀本次資料…"):
                text = summarize(market, result, articles, ai_key, context, provider=ai_settings["ai_provider"], model=ai_settings["ollama_model"])
            st.session_state["ai_report"] = dict(text=text, symbol=market["symbol"], interval=market["interval"],
                mode=market["mode"], candle=str(result["frame"].iloc[-1].close_time), sources=articles[:12])
        except Exception as exc:
            # Never surface response bodies or headers containing credentials.
            st.error(str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "AI 服務目前無法連線或回應格式異常。")
    report = st.session_state.get("ai_report")
    if report and (report["symbol"], report["interval"], report["mode"]) == (market["symbol"], market["interval"], market["mode"]):
        st.caption(f'摘要所用收盤資料：{report["candle"]} · 此為生成文字，需自行核對。')
        st.markdown(report["text"])
        with st.expander("本次摘要引用來源索引"):
            for index, article in enumerate(report["sources"], 1):
                st.write(f'[{index}] {article["source"]} — {article["title"]}')
                st.link_button("原始來源", article["url"], key=f"ai-source-{index}")


@st.fragment(run_every=60)
def render_dashboard(symbol, interval, mode):
    try:
        with st.spinner("整理市場資料與結構…"):
            market = cached_market(symbol, interval, mode)
            result = analyze(market)
            try:
                model = load_record(model_path(STATE_ROOT / "models", symbol, interval, market["mode"] == "demo"))
                result["decision"] = consensus(market, result, model)
            except (ValueError, KeyError, OSError):
                result["decision"] = consensus(market, result)
    except Exception as exc:
        st.error("目前無法取得有效行情。可切換示範模式檢視網站功能。")
        st.caption(str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "資料服務異常")
        return
    demo = market["mode"] == "demo"
    stamp = market["fetched_at"].astimezone(__import__("zoneinfo").ZoneInfo("Asia/Taipei")).strftime("%m/%d %H:%M:%S")
    st.markdown(f'<div class="eyebrow">DERIVATIVES INTELLIGENCE / BINANCE USDT PERPETUAL</div>'
                f'<div class="hero-title">讓每筆決策，都有依據<span style="color:#38e5bc">。</span></div>'
                f'<div class="subtle">{esc(symbol.removesuffix("USDT"))} / USDT &nbsp; · &nbsp; {esc(interval)} &nbsp; · &nbsp; '
                f'<span class="tag {"demo" if demo else "live"}">{"示範資料 · 非即時訊號" if demo else "LIVE 公開行情"}</span>'
                f' &nbsp; 更新 {stamp}（台北）</div><br>', unsafe_allow_html=True)
    if demo:
        st.warning("示範模式：價格、資金費率、持倉量均為合成資料，僅供測試介面與計算流程，不能據此交易。")
    st.caption(monitor_status(symbol, interval, mode))
    for key, message in market["errors"].items():
        st.caption(f"資料狀態 · {key}：{message}")
    frame = result["frame"]
    bars_24h = {"15m": 96, "1h": 24, "4h": 6}[interval]
    change = (frame.iloc[-1].close / frame.iloc[-1-bars_24h].close - 1) * 100
    cols = st.columns(4)
    with cols[0]:
        metric("最新已收盤價格 · USDT", price(result["entry"]), f"24 小時 {change:+.2f}%" + (" · 合成資料" if demo else ""))
    with cols[1]:
        metric("資金費率", f'{market["funding"]:+.4f}%' if market["funding"] is not None else "無資料", "當期費率，非年化；週期依交易所規則")
    with cols[2]:
        oi = market["oi_usd"]
        oi_change = market["oi_change"]
        metric("未平倉量 · USDT", f"{oi / 1e9:,.2f}B" if oi is not None else "無資料", f"近 30 樣本 {oi_change:+.2f}%" if oi_change is not None else "持倉資料不可用")
    with cols[3]:
        metric("RSI · 14", f'{frame.iloc[-1].rsi:.1f}', "超買 > 70 ／ 超賣 < 30")
    tabs = st.tabs(["市場總覽", "SMC / ICT 結構", "資金與成交", "AI 學習與模擬", "新聞與 AI", "風險試算", "方法與資料"])
    with tabs[0]:
        overview(market, result)
    with tabs[1]:
        structure_tab(result)
    with tabs[2]:
        flow_tab(market)
    with tabs[3]:
        learning_tab(market, result)
    with tabs[4]:
        news_tab(market, result, mode == "demo")
    with tabs[5]:
        risk_tab(market, result)
    with tabs[6]:
        st.markdown("### 資料透明，才有研究價值")
        st.markdown("""
| 項目 | 目前實作 |
|---|---|
| 行情來源 | Binance USDⓈ-M 公開 API；300 根 K 線，排除未收盤當根 |
| 更新機制 | 頁面每 60 秒刷新；一鍵啟動另開背景程序每 60 秒收集，新聞每 5 分鐘；非推播服務 |
| 規則分數 | 趨勢 ±2、RSI ±1、MACD ±1、突破 ±2、掃單 ±1、費率擁擠 ±1 |
| 方向門檻 | ≥ +4 偏多、≤ −4 偏空，其餘觀望；過期或缺失 K 線強制觀望 |
| SMC／ICT | 前 20 根區間突破與掃單、區間中點、三根 K 線 FVG（保留未完全回補區域） |
| 資金觀察 | 資金費率與名目 OI；不等同實際流入量或主力多空倉位 |
| AI | 可選 Ollama 本機／OpenAI 文字摘要；另有本機數值學習模型 |
| 持續學習 | 邏輯迴歸定期重訓、驗證集選參數、保存版本；收集到的 K 線以最近最多 5,000 根訓練，不自動改寫程式碼 |
| 驗證程度 | 學習頁提供有限歷史的時間切分回測與未來紙上紀錄；未經實盤績效驗證 |
| 全市場 | 全市場頁提供動態 USDT 永續合約掃描、排程學習、網站訊號與 Telegram 推播 |
| 尚未涵蓋 | 訂單簿、鏈上資金、宏觀日曆、完整 ICT、登入與真實下單 |
""")
        st.caption("分數不表示成功率。因子可能高度相關，未做統計校準。止盈止損是 ATR 假設，無法保證成交或控制極端行情損失。")
        st.json({"source": "synthetic" if demo else "Binance USD-M", "mode": market["mode"],
                 "symbol": symbol, "interval": interval, "last_closed_candle_utc": str(frame.iloc[-1].close_time),
                 "candles": len(frame), "data_valid": result["valid"], "errors": market["errors"]})
    snapshot = {"symbol": symbol, "interval": interval, "mode": market["mode"],
                "candle_utc": str(frame.iloc[-1].close_time), "score": result["score"], "side": result["side"],
                "entry": result["entry"], "stop": result["stop"], "targets": result["targets"],
                "factors": result["factors"], "limitations": result["reasons"], "consensus": result["decision"]}
    st.download_button("下載本次研究紀錄 · JSON", json.dumps(snapshot, ensure_ascii=False, indent=2),
                       file_name=f"{symbol}-{interval}-research.json", mime="application/json")
    st.markdown('<div class="footer">BTC NAVIGATOR / RESEARCH TERMINAL<br>合約交易可能導致全部保證金損失。研究訊號與 AI 文字均不保證收益，請獨立核對來源與風險。此版本不連接交易帳戶、不自動下單。</div>', unsafe_allow_html=True)


def main():
    st.set_page_config(page_title="BTC Navigator · 合約研究終端", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
    st.markdown(STYLE, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown('<div class="brand">◈ BTC<span>NAVIGATOR</span></div>',unsafe_allow_html=True)
        portal=st.radio('介面',['交易前台','研究後台'],key='portal')
    if portal=='交易前台':
        with st.sidebar:
            page=st.radio('前台功能',['交易訊號','行情查詢','自選清單'])
            st.caption('Binance USDT永續 · 僅紙上研究')
            st.caption('完整分析、學習與設定請切換研究後台。')
            st.markdown('<span class="tag">BUILD · 0.9</span>',unsafe_allow_html=True)
        from trading_frontend import frontend
        frontend(page)
        return
    st.caption('研究後台：分析、模擬紀錄、模型競賽與設定。此切換為介面整理，不是登入權限隔離。')
    if "pending_workspace" in st.session_state:
        st.session_state["workspace"] = st.session_state.pop("pending_workspace")
    if "pending_symbol" in st.session_state:
        st.session_state["selected_symbol"] = st.session_state.pop("pending_symbol")
        st.session_state["research_symbol"] = st.session_state["selected_symbol"]
    st.session_state.setdefault("workspace", "策略訊號台")
    with st.sidebar:
        st.markdown('<div class="brand">◈ BTC<span>NAVIGATOR</span></div><div class="brand-sub">INTELLIGENCE / TRADING RESEARCH</div>', unsafe_allow_html=True)
        st.caption("工作區 / MARKET WORKSPACE")
        workspace = st.radio("功能", ["策略訊號台", "全市場訊號", "互動決策台", "單幣研究", "學習與績效", "系統健康", "設定中心"], key="workspace", index=None)
        symbol = st.session_state.get("selected_symbol", os.environ.get("BTC_DEFAULT_SYMBOL", "BTCUSDT"))
        interval = os.environ.get("BTC_DEFAULT_INTERVAL", "1h")
        mode = "demo" if os.environ.get("BTC_NAVIGATOR_DEMO") == "1" else "auto"
        if workspace == "單幣研究":
            default_symbol = os.environ.get("BTC_DEFAULT_SYMBOL", "BTCUSDT")
            symbols = sorted(set(SYMBOLS) | set(discovered_symbols()) | {default_symbol} | {st.session_state.get("selected_symbol", default_symbol)})
            st.session_state.setdefault("selected_symbol", default_symbol)
            symbol = st.selectbox("交易對", symbols, index=None, key="selected_symbol", accept_new_options=True)
            symbol = symbol.strip().upper()
            intervals = ["15m", "1h", "4h"]
            default_interval = os.environ.get("BTC_DEFAULT_INTERVAL", "1h")
            interval = st.selectbox("分析週期", intervals, index=intervals.index(default_interval) if default_interval in intervals else 1)
            labels = ["自動（即時優先）", "僅即時資料", "示範資料"]
            selected = st.selectbox("資料模式", labels, index=2 if os.environ.get("BTC_NAVIGATOR_DEMO") == "1" else 0)
            mode = dict(zip(labels, ["auto", "live", "demo"]))[selected]
            st.caption("交易所：Binance USDⓈ-M 永續合約")
        else:
            st.caption("BINANCE / USDT PERPETUAL")
            st.caption("單幣選擇與行情來源請到「單幣研究」；全市場週期在設定中心管理。")
        if st.button("↻ 立即更新資料", width="stretch"):
            cached_market.clear()
            cached_news.clear()
            cached_context.clear()
            st.rerun()
        st.divider()
        st.markdown("**研究流程**")
        st.caption("01　確認資料來源\n\n02　觀察趨勢與市場結構\n\n03　核對新聞與資金條件\n\n04　評估停損與風險")
        st.divider()
        with st.expander("AI 摘要設定（選用）"):
            st.text_input("OpenAI API Key", type="password", key="ai_session_key", help="只保留於本次網頁連線，不寫入模型、紀錄或壓縮檔。也可用 AI_API_KEY 環境變數。")
            st.caption("Ollama 不需要此金鑰；到全市場設定選擇供應者。OpenAI 手動摘要才可能產生 API 費用。")
        st.markdown('<span class="tag">RESEARCH BUILD · 0.9</span>', unsafe_allow_html=True)
        st.caption("頁面開啟期間每 60 秒刷新。\n\n公開資料不需交易所 API Key。")
        st.caption("背景狀態請看「全市場訊號／系統健康」，推播與模型設定請到「設定中心」。")
    if workspace == "策略訊號台":
        from strategy_ui import strategy_page
        strategy_page()
    elif workspace == "全市場訊號":
        scanner_page()
    elif workspace == "互動決策台":
        from interactive_research import decision_desk
        decision_desk(sorted(set(SYMBOLS) | set(discovered_symbols())))
    elif workspace == "學習與績效":
        learning_page()
    elif workspace == "系統健康":
        health_page()
    elif workspace == "設定中心":
        hero("CONTROL / PREFERENCES", "設定你的研究工作站。", "管理全市場週期、模型與 Telegram。設定儲存在你的電腦，供背景程序讀取。", [("LOCAL SETTINGS", "")])
        settings_panel()
        from strategy_ui import settings_panel as strategy_settings_panel
        strategy_settings_panel()
    else:
        render_dashboard(symbol, interval, mode)


if __name__ == "__main__":
    main()

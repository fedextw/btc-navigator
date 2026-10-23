"""Learning and paper-validation interface, separated from the market dashboard."""
import json
from pathlib import Path
import altair as alt
import pandas as pd
import streamlit as st

from learning_lab import (train_and_evaluate, model_path, save_record, load_record,
                          current_prediction, update_paper_journal, trade_stats)
from market_data import load_history, import_history_csv
from runtime_config import STATE_ROOT



def learning_tab(market, result):
    st.markdown("### AI 學習實驗室")
    st.caption("流程：收集歷史 → 訓練集學習 → 驗證集選參數 → 保留測試集評估 → 新行情紙上驗證。沒有『訓練到保證準確』的機制。")
    demo = market["mode"] == "demo"
    symbol, interval = market["symbol"], market["interval"]
    path = model_path(STATE_ROOT / "models", symbol, interval, demo)
    try:
        record = load_record(path)
    except (OSError, ValueError):
        record = None
        st.error("本機模型紀錄無法讀取，請保留檔案供檢查後重新訓練。")
    st.info("學習模型採可解釋的邏輯迴歸基準，以 OHLCV 的 9 個特徵預測未來漲跌；與新聞生成式 AI 分開。新聞、費率與 OI 尚無帶時間戳的歷史庫，因此不納入此版歷史訓練。")
    with st.form("training-form"):
        source = st.radio("訓練資料", ["目前模式的歷史行情", "匯入歷史 CSV"], horizontal=True)
        uploaded = st.file_uploader("歷史 CSV（選用）", type=["csv"], help="800～5,000 根，2 MB 以內。欄位 time,open,high,low,close,volume；time 為 UTC ISO 或毫秒 Unix。週期須與左側選擇一致。")
        a, b, c = st.columns(3)
        horizon = a.selectbox("持有根數（下一根開盤進場）", [3, 6, 12], index=1)
        fee = b.number_input("訓練假設單邊手續費（%）", 0.0, 1.0, 0.05, 0.01)
        slippage = c.number_input("訓練假設單邊滑價（%）", 0.0, 1.0, 0.02, 0.01)
        train = st.form_submit_button("收集資料並訓練／重新評估", type="primary")
    if train:
        try:
            with st.spinner("擷取最多 1,500 根 K 線，以時間順序訓練與模擬…"):
                imported = source == "匯入歷史 CSV"
                if imported and uploaded is None:
                    raise ValueError("請先選取歷史 CSV")
                candles = import_history_csv(uploaded.getvalue(), interval) if imported else load_history(symbol, interval, demo)
                record = train_and_evaluate(candles, symbol, interval, demo if not imported else False, horizon, fee, slippage)
                record["input_source"] = "uploaded_csv" if imported else ("demo" if demo else "binance")
                if imported:
                    record["checks"]["匯入來源已由系統驗證"] = False
                    record["research_pass"] = False
                dataset = STATE_ROOT / "datasets" / f'{record["id"]}.csv'
                dataset.parent.mkdir(parents=True, exist_ok=True)
                candles.to_csv(dataset, index=False)
                save_record(STATE_ROOT / "models" / "archive" / f'{record["id"]}.json', record)
                if imported:
                    st.session_state[f"imported-{symbol}-{interval}"] = record
                else:
                    save_record(path, record)
            st.success("本輪訓練完成。請檢查測試集與未來紙上結果；即使通過研究門檻，也不代表適合實盤。")
        except Exception as exc:
            st.error(f"訓練未完成：{exc}" if isinstance(exc, (ValueError, RuntimeError)) else "資料取得或本機儲存失敗，原模型保留。")
    record = st.session_state.get(f"imported-{symbol}-{interval}", record)
    if not record:
        st.markdown("尚無此交易對／週期的模型。按上方按鈕開始；示範與真實模型分開保存。")
        st.caption("資料儲存在本機 .local-state（或指定的狀態目錄），未送往外部模型。重新訓練只用驗證集選參數；請勿反覆根據測試結果改策略，否則會污染測試集。")
        return
    stats = record["test_stats"]
    columns = st.columns(4)
    columns[0].metric("測試集交易筆數", stats["trades"])
    columns[1].metric("測試淨報酬 · 1× 名目", f'{stats["net_pct"]:+.2f}%')
    columns[2].metric("最大回撤", f'{stats["max_drawdown_pct"]:.2f}%')
    columns[3].metric("測試交易勝率", f'{stats["win_rate"]:.1f}%' if stats["win_rate"] is not None else "無交易")
    st.caption(f'訓練時間：{record["trained_at"]} · 模型 {record["id"]} · {"使用者匯入，來源未獨立驗證" if record.get("input_source") == "uploaded_csv" else "合成資料，不是實績" if record["demo"] else "歷史公開行情，不是實盤績效"}')
    if record["research_pass"]:
        st.success("本輪通過研究門檻，可以繼續紙上觀察；尚未驗證實盤可行性。")
    else:
        st.warning("本輪未通過研究門檻。只保留研究與紙上觀察，不將模型包裝成可實盤下單的訊號。")
    curve = pd.DataFrame({"交易序號": range(len(stats["curve"])), "權益指數": stats["curve"]})
    st.altair_chart(alt.Chart(curve).mark_area(line={"color": "#38e5bc"}, color="#38e5bc", opacity=.15).encode(
        x="交易序號:Q", y=alt.Y("權益指數:Q", scale=alt.Scale(zero=False)), tooltip=["交易序號:Q", "權益指數:Q"]
    ).properties(height=210).configure_view(stroke=None), width="stretch")
    st.caption("回測為不重疊的 1× 名目多／空交易，訊號收盤後下一根開盤進場，持有固定根數後收盤出場，扣雙邊費用與滑價；不使用 ATR 出場、不模擬槓桿強平、資金費率或真實撮合。")
    checks = pd.DataFrame([{"檢驗": key, "結果": "通過" if value else "未通過"} for key, value in record["checks"].items()])
    left, right = st.columns(2)
    with left:
        st.dataframe(checks, hide_index=True, width="stretch")
    with right:
        st.write(f'**上漲機率 Brier 誤差：** {record["brier"]:.4f}')
        st.write(f'**固定訓練比例基準誤差：** {record["baseline_brier"]:.4f}')
        st.caption("誤差越低越好。模型機率未經校準，不等同下單勝率；固定比例基準以訓練集的漲幅比例估計，不使用測試集調整。")
        st.write(f'**驗證集選出的機率門檻：** {record["threshold"]:.0%}')
        pf = stats["profit_factor"]
        st.write(f'**Profit factor：** {pf:.2f}' if pf is not None else '**Profit factor：** 無法估計（無虧損樣本或無交易）')
    st.markdown("#### 下一階段：真正等待未來行情")
    if record.get("input_source") == "uploaded_csv":
        st.info("匯入資料只作離線評估，不與目前網站行情混用，也不取代背景監控模型。切換交易對或重新整理網頁可回到監控模型。")
        if st.button("回到目前監控模型"):
            st.session_state.pop(f"imported-{symbol}-{interval}", None)
            st.rerun()
    elif result["valid"]:
        try:
            prediction = current_prediction(record, market["candles"])
            st.write(f'本根模型觀察：**{prediction["side"]}** · 上漲模型輸出 **{prediction["probability"]:.1%}** · 僅供紙上驗證')
            journal_path = model_path(STATE_ROOT / "paper", symbol, interval, demo)
            journal = update_paper_journal(journal_path, record, market["candles"])
            closed = [r for r in journal["rows"] if r["status"] == "closed"]
            forward = trade_stats(closed)
            a, b, c = st.columns(3)
            a.metric("已結算紙上交易", forward["trades"])
            b.metric("紙上累積淨報酬", f'{forward["net_pct"]:+.2f}%')
            c.metric("等待未來行情", sum(r["status"] == "pending" for r in journal["rows"]))
            if journal["rows"]:
                st.dataframe(pd.DataFrame(journal["rows"]).tail(30), hide_index=True, width="stretch")
            else:
                st.caption("尚無未來交易。模型訓練視窗結束後，有新收盤 K 線且方向條件成立才會記錄，下一根開盤才可成交。")
            st.caption("模型重訓不會回寫既有紙上預測。網頁開啟時會更新；持續收集可另用 collector.py 背景程序。資料中斷導致無法還原進場時，標記 unresolved，不補造績效。")
        except (ValueError, OSError, KeyError) as exc:
            st.error(f"紙上紀錄暫時無法更新：{type(exc).__name__}")
    else:
        st.warning("目前行情不完整或過期，停止產生新的模型觀察與紙上進場。")
    with st.expander("查看資料切分、候選參數與測試交易"):
        st.json(record["split"])
        st.caption("約 60% 訓練／20% 驗證／20% 測試，分割邊界保留持有期隔離。測試集不參與門檻挑選。最近 1,500 根屬有限市場樣本，未覆蓋所有行情。")
        st.dataframe(pd.DataFrame(record["candidates"]), hide_index=True)
        st.dataframe(pd.DataFrame(record["trades"]), hide_index=True)
    st.download_button("下載本輪完整模型與評估紀錄", json.dumps(record, ensure_ascii=False, indent=2),
                       file_name=f'{symbol}-{interval}-model-{record["id"]}.json', mime="application/json")

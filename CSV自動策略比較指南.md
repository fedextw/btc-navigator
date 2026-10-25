# 自動 CSV 策略比較｜B＋C 第二批

這是**已可執行的離線研究工具**，不是完整自主 Agent。與原本 BTC Navigator 前台／實盤權限隔離。

使用 CSV 欄位：`time,open,high,low,close,volume`。時間為 UTC ISO8601，至少300根、按時間遞增且已收盤的 K 線。資料真實性由使用者提供，程式不下載市場資料。

在專案資料夾中開 CMD：

```bat
py -3.13 -m unittest discover -s tests -p test_agent_csv_research.py -v
py -3.13 agent_csv_research.py your_candles.csv --output test_research_result.json
```

第二行須將 `your_candles.csv` 改為真實 CSV 的路徑。

目前比較兩項**預先固定策略**：10／50 收盤均值方向策略、20 根收盤突破策略。依60%研究暖身／20%驗證／20%保留測試進行；只用驗證績效挑選策略，保留段用來確認。訊號在當根收盤取得，下一根開盤模擬入場，第三根收盤出場，預設雙邊合計交易成本 0.14%（可用 `--cost` 指定小數）。不模擬槓桿強平、深度成交、逐筆資金費、交易所限制；預設假設並不代表實際成本。

研究 JSON 包含資料 SHA-256、候選策略、驗證與保留績效、審核結果。程式以新檔方式保存結果，避免覆蓋已有研究紀錄。

**重要限制**：`requires_independent_replication` 也只是紙上研究候選，不會晉升或提供新下單指令。尚未提供 AI 自動產生新程式、歷史行情來源驗證或背景排程。請勿將本模組結果當作真實資金交易建議。

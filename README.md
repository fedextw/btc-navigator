# BTC Navigator｜持續學習的合約研究網站

**[下載一鍵啟動 ZIP](https://github.com/fedextw/btc-navigator/raw/refs/heads/codex/btc-navigator-delivery/releases/BTC-Navigator.zip)** · [下載與啟動說明](releases/README.md)

繁體中文 Binance USDT 永續合約研究終端。包含技術指標、SMC／ICT 簡化結構、公開新聞、市場資金脈絡、機器學習、歷史回測、未來紙上驗證及背景收集。**這是研究軟體，不是已證實能獲利的自動交易產品。**

## 一鍵啟動

1. 安裝 **Python 3.11 或更新版本**（建議 3.11）；Windows 安裝時勾選 **Add Python to PATH**。
2. 將整個 ZIP 解壓縮到可寫入的資料夾，不能直接從 ZIP 內執行。
3. Windows 雙擊 `啟動.bat`；macOS 雙擊 `啟動.command`；Linux 執行 `bash 啟動.sh`。
4. 首次會連網下載固定版本套件，之後自動開啟瀏覽器並啟動背景研究。若瀏覽器未自動開啟，依終端顯示的本機地址開啟。

macOS 若沒有執行權限，在終端執行 `chmod +x 啟動.command`，再雙擊。首次需可連線 PyPI，不需要 Docker、Node.js 或交易所金鑰。**沒有內附 Python 或獨立 EXE**；Windows／macOS 啟動檔未經原生平台實機驗證，Linux 已測試。

保留啟動視窗，關閉瀏覽器後背景程序仍可執行。按 **Ctrl+C** 結束網站與背景程序。電腦關機、休眠、網路中斷或雲端機器停止時不能持續監控；本包不會安裝作業系統服務或自動開機程序。

### 沒有即時連線時先試用

在資料夾內執行 `python launch.py --demo`（macOS／Linux 用 `python3`）。所有合成行情與紙上紀錄都會標示為示範，並與真實資料分開。範例 CSV 檔名也明確標示為合成資料。

### 更換背景監控標的

預設 **BTCUSDT／1h**。例如：`python launch.py --symbol ETHUSDT --interval 4h`。可選 BTC、ETH、SOL、BNB、XRP、DOGE；週期 15m、1h、4h。**網頁切換交易對只改變畫面，不會更改已啟動的背景程序。** 一個啟動器監控一個交易對／週期。換標的先 Ctrl+C 停止原程序再啟動。

## 已提供的功能

| 功能 | 內容 |
|---|---|
| 技術與訊號 | 已收盤 K 線、EMA 20/50/200、RSI、MACD、ATR、成交量、可解釋規則分數 |
| SMC／ICT | 前 20 根區間突破、流動性掃單、Premium／Discount、未完全回補 FVG；是簡化啟發式，不是完整 ICT 模型 |
| 資金觀察 | 當期資金費率、名目 OI、主動買賣成交差額與視窗 CVD、累積 OI 快照 |
| 新聞 | CoinDesk、Cointelegraph、Decrypt 公開 RSS；原始連結與發布時間，不杜撰失敗來源的新聞 |
| 全球背景 | CoinGecko 全球市值／成交量／BTC 市佔、DefiLlama 穩定幣供給與 DeFi TVL、Alternative.me 恐懼貪婪指數 |
| 機器學習 | 9 個 OHLCV 特徵的邏輯迴歸；3 組正則化 × 3 組門檻，僅用驗證集選參數 |
| 回測 | 時序 60/20/20 切分、邊界持有期隔離、下一根開盤進場、扣雙邊費率及滑價、不重疊持倉 |
| 未來紙上驗證 | 先保存預測，等未來行情才能進場與結算；重訓不回寫舊預測；資料斷層不補造績效 |
| 研究共識 | 真實且有效行情、模型通過研究門檻、模型未過期、行情超出訓練視窗、規則與模型同向才顯示方向；其餘觀望 |
| 風險試算 | 權益、單筆風險、進場、停損、手續費、名目部位與保證金估算 |
| 匯入／匯出 | 歷史 CSV 回測；JSON 研究紀錄／模型下載；匯入資料不覆蓋即時模型 |
| 一鍵啟動 | 獨立套件環境、自動開瀏覽器、背景程序、心跳、SQLite 與模型版本保存 |

## 持續學習如何運作

- 背景程序每 **60 秒** 收集公開行情與快照，RSS 最快每 **5 分鐘**、全球背景每 **15 分鐘** 收集一次。
- 首次啟動自動取得最多 **1,500 根** 歷史 K 線並訓練；持續把收集的 K 線存入本機 SQLite。往後訓練可使用累積的最近最多 **5,000 根**。
- 距上次訓練至少 **24 小時**、且至少多出 **24 根新收盤 K 線**，才自動重新訓練並選參數。1h 約每天、4h 至少四天；不是每分鐘重訓。
- 每版保存資料指紋、參數、測試交易與評估，可對照後續紙上結果。模型版本和資料保存在 `.local-state`；不會自行改寫原始碼。
- 模型預測只用歷史 OHLCV。新聞、情緒、費率、OI、穩定幣／TVL 是即時研究背景，**尚未累積成可用來訓練的時間對齊歷史特徵**，因此不把現在的資料填回過去。
- 「持續學習」代表重新擬合與持續評估，**不代表每次重訓都會變得更準，也不保證勝率或收益**。反覆觀看／調整同一測試集會造成過度擬合；真正重要的是之後未曾看過的市場與紙上結果。

回測是固定持有期的 **1× 名目研究策略**，與總覽中的 ATR 研究價位不同。未模擬資金費結算、強平、真實撮合、跳空與極端流動性；不能當成槓桿合約實盤績效。

## 生成式 AI 新聞／市場解讀（選用）

學習、監控與回測不需付費 AI 金鑰。需要文字摘要時，可在側欄「AI 摘要設定」輸入自己的 OpenAI API Key，只保存於當次連線記憶體；或在作業系統安全設定 `AI_API_KEY`。不要把金鑰傳到聊天、寫進原始碼或打包分享。

手動點「產生本次 AI 研究摘要」才會把目前的指標、來源標題與市場背景傳送到 OpenAI。預設模型 `gpt-4.1-mini`，可用 `AI_MODEL` 環境變數更換帳戶可用的模型。**可能產生 API 費用。** 摘要不是新聞全文閱讀結果，也不會改變已記錄的規則分數或替你下單。未設定金鑰時不會假裝已呼叫 AI。

## CSV 格式

必備標題：`time,open,high,low,close,volume`。time 使用 UTC ISO 時間或毫秒 Unix；800～5,000 根、2 MB 以內、時間連續、OHLC 合理。左側週期需和資料一致。缺少的收盤時間依週期計算，不會補造價格。匯入資料只做離線研究，來源未經系統獨立驗證，不會取得即時訊號資格。

## 資料來源與限制

| 來源 | 用途／連線主機 |
|---|---|
| Binance USDⓈ-M | `fapi.binance.com`：K 線、premiumIndex、openInterestHist |
| CoinDesk | `www.coindesk.com`：公開 RSS |
| Cointelegraph | `cointelegraph.com`：公開 RSS |
| Decrypt | `decrypt.co`：公開 RSS |
| CoinGecko | `api.coingecko.com`：global API |
| DefiLlama | `stablecoins.llama.fi`、`api.llama.fi`：供給與 TVL |
| Alternative.me | `api.alternative.me`：情緒指數 |
| OpenAI（選用） | `api.openai.com`：生成式研究摘要 |
| PyPI（首次安裝） | `pypi.org`、`files.pythonhosted.org` |

僅使用公開 API／RSS，不登入、繞過付費牆或擷取交易帳戶。各來源可有地區限制、流量上限或格式變更；失敗時顯示來源不可用，只有「自動」畫面模式可明確回退為合成行情，真實背景程序不會回退。資料來源不是全球所有網站的完整覆蓋。

OI 不是多空淨持倉；主動成交差額不是交易所淨入金；穩定幣供給不是入金；TVL 會受價格變動影響。未整合付費鏈上資金、全市場訂單簿、完整操盤策略庫、登入權限、雲端代管或通知推播。**沒有自動下單或交易所私鑰需求。**

## 驗證與故障排除

`python launch.py --check` 安裝並檢查環境。安裝後可用 `.launcher-venv/bin/python -m unittest discover -s tests -v`；Windows 路徑為 `.launcher-venv\Scripts\python.exe`。

背景狀態見網站心跳與 `.local-state/collector.log`；資料庫為 `.local-state/research.sqlite3`，模型／版本為 `models/`，歷史 CSV 為 `datasets/`，紙上紀錄為 `paper/`。請備份整個 `.local-state`；換機器不會自動同步。不可同時開兩個啟動器監控同一交易對／週期。連接埠衝突可用 `python launch.py --port 8502`。

本次驗證詳見 `驗證報告.md`。雲端測試期間外部金融／新聞網域受網路政策阻擋，不能把合成資料測試宣稱成真實市場績效。下載後若當地網路允許，啟動器會嘗試公開來源；若仍被封鎖，請檢查合法可用的網路設定與來源服務狀態，不要關閉 TLS 驗證。

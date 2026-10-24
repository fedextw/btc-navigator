# 一鍵啟動包下載

目前為 **1.0 AI強化實驗室版**。[完整首次使用指南與 Telegram 設定](../使用指南.md)。

**[點此下載 BTC-Navigator.zip](https://github.com/fedextw/btc-navigator/raw/refs/heads/codex/btc-navigator-delivery/releases/BTC-Navigator.zip)**

若直接下載沒有開始，開啟 [ZIP 檔案頁](https://github.com/fedextw/btc-navigator/blob/codex/btc-navigator-delivery/releases/BTC-Navigator.zip)，點右上角 **Download raw file**。私人儲存庫需先登入有權限的 GitHub 帳號。

1. 將整個 ZIP 解壓縮。
2. 安裝 Python 3.11 以上。
3. Windows 雙擊 **`START.bat`**；macOS 雙擊 `啟動.command`；Linux 執行 `bash 啟動.sh`。

新版啟動檔會保留錯誤視窗，並保存 `startup.log`。請完整解壓縮到新資料夾，勿直接雙擊 `launch.py`。如果啟動失敗，查看 `startup.log` 最後的實際錯誤。

首次會下載套件，之後啟動本機網站與背景研究。操作說明及驗證限制在壓縮檔內的 `README.md`、`驗證報告.md`。

首次啟動到「設定中心」設定 Telegram Token／Chat ID，保存後先按測試通知。Ollama 本機解讀不需 OpenAI Key；先依 [本機 AI 教程](../Ollama本機AI操作教程.md) 安裝並下載模型，再在網站設定、儲存與測試。既有使用者可把舊版 `.local-state` 複製到新版以保留學習紀錄，不要分享該資料夾。

這裡提供的是可下載程式，不是對外託管的網站。GitHub 不會直接執行 Streamlit；公開網站仍需部署到持續運行的 Python 主機。預設全市場 USDT 永續合約、1h、每輪 60 秒，首次模型排隊準備；符合條件才發研究訊號。依你的選擇只做紙上模擬，不能保證每天勝率或獲利都增加。

檔案雜湊見 `BTC-Navigator.zip.sha256`。ZIP 不包含金鑰、本機模型或監控紀錄。

0.4 的訓練追蹤、紙上紀錄匯出及資金成本情境，請看 [新版指南](../新版介面與績效指南.md)。

0.5 功能說明與如何核對新研究證據，請看 [互動研究指南](../互動研究與驗證指南.md)。新條件先做影子觀察，不代表勝率已提升。

0.6 分類點位、策略風險與AI學習，請看 [雙策略指南](../雙策略與75目標使用指南.md)。目標檢驗需要足夠事前記錄的未來樣本，不能保證勝率。

0.7成長中心、模型競賽與互動圖表，請看[新版指南](../AI成長中心與獲利風險指南.md)。取消75%勝率目標，不代表已驗證獲利提高。

0.8浮動風險、報價資料品質及成本來源，請看[新版指南](../即時風險與成交成本指南.md)。

0.9預設交易前台，完整研究功能從左側切到後台。[操作指南](../前後台操作指南.md)。這是介面分區，不是登入權限隔離。

1.0六類模型研究、行情適配與退化防護，請看[新版指南](../AI強化實驗室操作指南.md)。沒有新增付費API或模型下載；至少300筆合格結算才研究新家族，並不保證進步或獲利。

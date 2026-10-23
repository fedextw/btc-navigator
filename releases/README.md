# 一鍵啟動包下載

目前為 **0.2 全市場自動研究／模擬學習版**。[完整首次使用指南與 Telegram 設定](../使用指南.md)。

**[點此下載 BTC-Navigator.zip](https://github.com/fedextw/btc-navigator/raw/refs/heads/codex/btc-navigator-delivery/releases/BTC-Navigator.zip)**

若直接下載沒有開始，開啟 [ZIP 檔案頁](https://github.com/fedextw/btc-navigator/blob/codex/btc-navigator-delivery/releases/BTC-Navigator.zip)，點右上角 **Download raw file**。私人儲存庫需先登入有權限的 GitHub 帳號。

1. 將整個 ZIP 解壓縮。
2. 安裝 Python 3.11 以上。
3. Windows 雙擊 **`START.bat`**；macOS 雙擊 `啟動.command`；Linux 執行 `bash 啟動.sh`。

新版啟動檔會保留錯誤視窗，並保存 `startup.log`。請完整解壓縮到新資料夾，勿直接雙擊 `launch.py`。如果啟動失敗，查看 `startup.log` 最後的實際錯誤。

首次會下載套件，之後啟動本機網站與背景研究。操作說明及驗證限制在壓縮檔內的 `README.md`、`驗證報告.md`。

首次啟動到「全市場訊號」設定 Telegram Token／Chat ID，保存後先按測試通知。OpenAI 自動解讀為選用，需自己的 API Key、啟用及設定每日上限。既有使用者可把舊版 `.local-state` 複製到新版以保留學習紀錄，不要分享該資料夾。

這裡提供的是可下載程式，不是對外託管的網站。GitHub 不會直接執行 Streamlit；公開網站仍需部署到持續運行的 Python 主機。預設全市場 USDT 永續合約、1h、每輪 60 秒，首次模型排隊準備；符合條件才發研究訊號。依你的選擇只做紙上模擬，不能保證每天勝率或獲利都增加。

檔案雜湊見 `BTC-Navigator.zip.sha256`。ZIP 不包含金鑰、本機模型或監控紀錄。

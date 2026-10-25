# B＋C 多 Agent 自主研究｜第一批安全接入

本模組是一個可執行的 **Agent 研究提案驗收入口**，與現有 BTC Navigator 訊號、模擬帳本、Telegram 與下單邏輯完全隔離。

## 使用

把外部 Agent（Codex、Claude Code 或研究 Agent）研究所得的數據整理為 JSON，欄位見 `tests/test_agent_research_gate.py` 的 `example()`。之後執行：

```bash
python agent_research_gate.py proposal.json --audit-dir .local-state/agent-audit
python -m unittest tests.test_agent_research_gate -v
```

結果只有 `eligible_for_independent_review` 或 `rejected`。前者代表**提案填寫的證據通過初步資料門檻**，不是統計上已驗證獲利，更不是可以修改正式策略、推播新入場點或真實下單的許可。審核器目前**不會主動執行回測、讀取交易所或核驗模型結果**；Agent 的自陳數據仍需獨立回測和人員核對。

## 安全邊界

- 所有審核結果 `live_trading_authorized` 固定為 `false`。
- 不連結交易 API，不接受金鑰，不修改既有 `.local-state` 資料庫。
- 提案檢查訓練／測試時間分界、最低樣本、成本後報酬、回撤、獲利因子、前視偏差與保留測試是否被挪用。
- 審查採 fail-closed：缺資料不通過；不合型別、不合法時間與 NaN 直接失敗。
- 稽核檔按提案原始 SHA-256 建立，不覆蓋既有紀錄。
- 下一批才會把可重現回測產生的證據、自動測試輸出與 Agent 任務排程接入，並需要完整檢查既有交易管線。

此版本沒有自動改寫策略、模型晉升或自動交易功能。驗收以實際測試結果為準。

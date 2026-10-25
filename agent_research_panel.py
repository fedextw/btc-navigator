"""Read-only, bounded status parser for Streamlit agent research panel."""
import json
from pathlib import Path

MAX_STATUS_BYTES = 256_000
MAX_ITEMS = 10


def load_status(state_root):
    path = Path(state_root) / "agent-status" / "latest.json"
    if not path.is_file():
        return {"state": "not_started", "items": [], "message": "尚無排程紀錄；研究排程器尚未啟用。"}
    if path.stat().st_size > MAX_STATUS_BYTES:
        return {"state": "invalid", "items": [], "message": "狀態檔案大小異常，拒絕顯示。"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != "agent-scheduler-v1" or payload.get("live_trading_authorized") is not False:
            raise ValueError("不認得的狀態版本或交易授權欄位")
        phase = payload.get("phase", "completed")
        if phase not in ("running", "completed", "error"):
            raise ValueError("不認得的研究執行階段")
        items = payload["items"]
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise ValueError("研究項目格式不正確")
        clean = []
        for item in items:
            if not isinstance(item, dict) or item.get("status") not in ("completed", "skipped"):
                raise ValueError("研究紀錄格式不正確")
            outcome = item.get("result") or {}
            proposal = outcome.get("proposal_research") if isinstance(outcome.get("proposal_research"), dict) else {}
            clean.append({"symbol": str(item.get("symbol",""))[:32], "at": str(item.get("at",""))[:40],
                "status": item["status"], "selected": str(outcome.get("selected") or "—")[:64],
                "proposal_status": str(proposal.get("status") or "未啟用")[:64],
                "proposal_selected": str(proposal.get("selected") or "—")[:64],
                "decision": str(outcome.get("status") or "—")[:64],
                "reason": str(outcome.get("reason") or item.get("error_type") or "—")[:160],
                "bars": outcome.get("bars") if isinstance(outcome.get("bars"), int) else None})
        text = {"running":"研究程序正在執行（如長時間不更新，請檢查研究日誌）。",
                "completed":"最近一次研究批次（只讀）",
                "error":"最近一次研究程序出錯，請檢查 agent-research.log。"}[phase]
        return {"state":"available" if phase == "completed" else phase, "phase":phase, "items":clean, "message":text,
                "started_at":str(payload.get("started_at") or "")[:40],
                "finished_at":str(payload.get("finished_at") or "")[:40]}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError):
        return {"state":"invalid", "items":[], "message":"研究狀態格式不正確，未採用任何交易訊號。"}


def render(state_root):
    import streamlit as st
    st.title("AI Agent 研究中心")
    st.caption("僅顯示獨立研究排程的結果。不提供新下單訊號、不修改模型，也不自動啟動排程。")
    # Read-only local diagnostic: show service state without exposing secrets.
    from agent_bc_diagnostic import inspect
    health = inspect(state_root, 8591)
    st.subheader("B＋C 本機健康檢查")
    cols = st.columns(3)
    cols[0].metric("網站連接埠", "有回應" if health["website_port_responds"] else "無回應")
    cols[1].metric("掃描紀錄", "已建立" if health["scanner_log_exists"] else "尚未建立")
    cols[2].metric("Agent 狀態", {"running":"研究中","completed":"已完成",
                   "error":"發生錯誤","missing":"尚無紀錄"}.get(health["agent_status"],"需檢查"))
    st.caption(health["recommendation"])
    st.caption("健康燈號只能確認基本啟動，不代表行情持續更新、研究品質或可實盤下單。")
    record = load_status(state_root)
    st.info(record["message"])
    if record.get("started_at"):
        st.caption("研究開始（UTC）：" + record["started_at"])
    if record.get("finished_at"):
        st.caption("最後完成（UTC）：" + record["finished_at"])
    if record["items"]:
        st.dataframe(record["items"], use_container_width=True, hide_index=True)
    st.caption("研究結果為模擬研究，不代表可成交績效；正式策略與交易系統未獲得任何新授權。")

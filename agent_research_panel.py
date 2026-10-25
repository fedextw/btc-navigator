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
            backfill = item.get("backfill") if isinstance(item.get("backfill"), dict) else {}
            evidence = outcome.get("profitability_evidence") if isinstance(outcome.get("profitability_evidence"),dict) else {}
            heldout = outcome.get("heldout_metrics") if isinstance(outcome.get("heldout_metrics"),dict) else {}
            clean.append({"symbol": str(item.get("symbol",""))[:32], "at": str(item.get("at",""))[:40],
                "status": item["status"], "selected": str(outcome.get("selected") or "—")[:64],
                "proposal_status": str(proposal.get("status") or "未啟用")[:64],
                "proposal_selected": str(proposal.get("selected") or "—")[:64],
                "backfill": {"not_requested":"未啟用","attempted":"已嘗試","completed":"補資料完成",
                             "failed":"補資料失敗","waiting_database":"等待資料庫"}.get(backfill.get("status"),"未啟用"),
                "backfill_inserted": backfill.get("inserted") if isinstance(backfill.get("inserted"), int) else 0,
                "decision": str(outcome.get("status") or "—")[:64],
                "profitability_gate": ("等待獨立前向模擬" if evidence.get("eligible") is True else
                                       "未通過／證據不足" if evidence else "尚無審核"),
                "heldout_trades": heldout.get("trades") if type(heldout.get("trades")) is int else None,
                "net_expectancy_r": round(heldout["net_expectancy_r"],4) if type(heldout.get("net_expectancy_r")) in (int,float) and abs(heldout["net_expectancy_r"]) < 1e9 else None,
                "reason": ("等待研究資料累積（需至少 300 根連續 K 棒）" if item.get("error_type") == "DataNotReady" else str(outcome.get("reason") or item.get("error_type") or "—")[:160]),
                "bars": outcome.get("bars") if isinstance(outcome.get("bars"), int) else None})
        text = {"running":"研究程序正在執行（如長時間不更新，請檢查研究日誌）。",
                "completed":"最近一次研究批次（只讀）",
                "error":"最近一次研究程序出錯，請檢查 agent-research.log。"}[phase]
        return {"state":"available" if phase == "completed" else phase, "phase":phase, "items":clean, "message":text,
                "started_at":str(payload.get("started_at") or "")[:40],
                "finished_at":str(payload.get("finished_at") or "")[:40],
                "counts": payload.get("counts") if isinstance(payload.get("counts"),dict) else None}
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
    from agent_forward_health_summary import inspect_forward_health
    forward_health=inspect_forward_health(state_root)
    st.caption("前向研究健康：" + forward_health["message"])
    st.caption("研究更新檢查：" + forward_health["freshness"] + "；執行鎖定：" + forward_health["lock"])
    st.caption("健康燈號只能確認基本啟動，不代表行情持續更新、研究品質或可實盤下單。")
    from agent_data_readiness import summarize
    with st.expander("USDT 合約研究資料就緒情況", expanded=True):
        readiness = summarize(state_root)
        metrics = st.columns(3)
        metrics[0].metric("已有 K 棒的 USDT 合約", readiness["observed_pairs"])
        metrics[1].metric("達 300 根門檻", readiness["enough_bars"])
        metrics[2].metric("抽查連續性合格", f'{readiness["ready_in_checked"]} / {readiness["checked_pairs"]}')
        if readiness["ready_examples"]:
            st.caption("抽查合格範例：" + "、".join(readiness["ready_examples"]))
        st.caption(readiness["note"] + "；以上只讀取本機資料，不會觸發補資料或交易。")
    record = load_status(state_root)
    st.info(record["message"])
    if record.get("started_at"):
        st.caption("研究開始（UTC）：" + record["started_at"])
    if record.get("finished_at"):
        st.caption("最後完成（UTC）：" + record["finished_at"])
    if record.get("counts"):
        counts = record["counts"]
        summary = st.columns(3)
        summary[0].metric("本批研究完成", counts.get("completed",0))
        summary[1].metric("等待資料", counts.get("waiting",0))
        summary[2].metric("其他略過", counts.get("skipped_other",0))
    if record["items"]:
        st.dataframe(record["items"], use_container_width=True, hide_index=True)
    st.subheader("獨立前向模擬績效")
    from agent_forward_dashboard import summarize_forward
    forward = summarize_forward(state_root)
    if forward["rows"]:
        st.dataframe(forward["rows"],use_container_width=True,hide_index=True)
    else:
        st.info("尚無已登記的前向模擬策略，不能推論已有模擬獲利。")
    st.caption("僅為離線假設成交估算；非真實成交，尚未計入完整資金費率及實際滑價。")
    st.caption("研究結果為模擬研究，不代表可成交績效；正式策略與交易系統未獲得任何新授權。")

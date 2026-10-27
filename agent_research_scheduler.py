"""Conservative opt-in research scheduler; separated from scanner and trading.

Never launches automatically. Invoke as a dedicated offline worker only after review.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from agent_state_research import run_from_state


def run_once(state_dir, symbols=("BTCUSDT",), interval="1h", mode="live", runner=run_from_state, proposal_runner=None, backfill_runner=None, backfill_limit=2):
    """Bounded batch, log each attempt, never interrupt other symbols after one failure."""
    from agent_symbol_validation import valid_symbol
    if interval not in ("15m", "1h", "4h") or mode not in ("demo", "live"):
        raise ValueError("研究參數不正確")
    if not 1 <= len(symbols) <= 10 or len(set(symbols)) != len(symbols) or not all(valid_symbol(s) for s in symbols):
        raise ValueError("研究幣種必須為1至10個不同合約")
    if not 0 <= backfill_limit <= 2:
        raise ValueError("每輪補資料最多2個合約")
    backfill_used = 0
    output = []
    for symbol in symbols:
        started = datetime.now(timezone.utc).isoformat()
        backfill_info = {"status":"not_requested"}
        try:
            try:
                item = runner(state_dir, symbol, interval, mode)
            except (FileNotFoundError, ValueError) as first_error:
                data_missing = isinstance(first_error, FileNotFoundError) or (
                    isinstance(first_error, ValueError) and "不足 300 根" in str(first_error))
                if not data_missing or mode != "live" or backfill_runner is None or backfill_used >= backfill_limit:
                    raise
                backfill_used += 1
                # Strict bounded retry: only once after one public-data request.
                backfill_info = {"status":"attempted"}
                result = backfill_runner(state_dir, symbol, interval)
                if isinstance(result, dict):
                    backfill_info = {"status":str(result.get("status","attempted"))[:32],
                                     "inserted":max(0,int(result.get("inserted",0)))}
                item = runner(state_dir, symbol, interval, mode)
            if proposal_runner is not None:
                item = dict(item)
                try:
                    item["proposal_research"] = proposal_runner(state_dir, symbol, interval, mode)
                except (ValueError, OSError, RuntimeError) as exc:
                    item["proposal_research"] = {"status": "skipped", "error_type": type(exc).__name__, "live_trading_authorized": False}
            # Freeze the research cutoff before any future paper evaluation.
            # Failed freezing cannot grant trading permission or silently
            # relabel the underlying research as a success.
            if mode=="live" and item.get("status")=="research_candidate":
                from agent_forward_freeze import freeze_candidate
                try:
                    item=dict(item)
                    item["forward_baseline"]=freeze_candidate(state_dir,item)
                except (ValueError,OSError,RuntimeError) as exc:
                    item=dict(item)
                    item["forward_baseline"]={"status":"freeze_failed",
                                              "error_type":type(exc).__name__,
                                              "live_trading_authorized":False}
            output.append({"symbol":symbol,"at":started,"status":"completed",
                           "backfill":backfill_info,"result":item})
        except (ValueError, OSError, RuntimeError) as exc:
            waiting = isinstance(exc, FileNotFoundError) or (isinstance(exc, ValueError) and "不足 300 根" in str(exc))
            if backfill_info["status"] == "attempted":
                backfill_info = {"status":"failed","error_type":type(exc).__name__}
            output.append({"symbol":symbol,"at":started,"status":"skipped",
                           "backfill":backfill_info,
                           "error_type":"DataNotReady" if waiting else type(exc).__name__})
    counts = {"attempted":len(output),
              "completed":sum(x["status"] == "completed" for x in output),
              "waiting":sum(x.get("error_type") == "DataNotReady" for x in output),
              "skipped_other":sum(x["status"] == "skipped" and x.get("error_type") != "DataNotReady" for x in output)}
    return {"schema":"agent-scheduler-v1","paper_only":True,"live_trading_authorized":False,"items":output,
            "counts":counts,"finished_at": datetime.now(timezone.utc).isoformat()}


def write_status(state_dir, report):
    directory = Path(state_dir) / "agent-status"
    directory.mkdir(parents=True, exist_ok=True)
    # Non-authoritative status only: never controls promotion or execution.
    target = directory / "latest.json"
    import os
    import tempfile
    with tempfile.NamedTemporaryFile("w",dir=directory,encoding="utf-8",suffix=".tmp",delete=False) as f:
        temporary=f.name
        json.dump(report,f,ensure_ascii=False,allow_nan=False,indent=2)
    os.replace(temporary,target)
    return target


def main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser=argparse.ArgumentParser(description="BTC Navigator 獨立離線研究排程（僅紙上）")
    parser.add_argument("--state-dir",default=".local-state")
    parser.add_argument("--symbols",nargs="+",default=["BTCUSDT"])
    parser.add_argument("--interval",choices=("15m","1h","4h"),default="1h")
    parser.add_argument("--mode",choices=("live","demo"),default="live")
    parser.add_argument("--once",action="store_true",help="只執行一輪")
    parser.add_argument("--auto-universe",action="store_true",help="輪流研究資料庫內已累積足夠行情的 USDT 合約（每批最多10種）")
    parser.add_argument("--retry-minutes",type=int,default=30,help="全批資料未就緒時重新檢查的分鐘數")
    parser.add_argument("--backfill-missing",action="store_true",help="選用公開行情補資料，每輪最多兩種幣，不適用示範模式")
    parser.add_argument("--proposal-research", action="store_true", help="同時執行受控候選研究（預設關閉）")
    parser.add_argument("--hours",type=int,default=24,help="研究間隔（最短6小時）")
    args=parser.parse_args()
    if not 6 <= args.hours <= 168: parser.error("研究間隔必須6至168小時")
    if not 5 <= args.retry_minutes <= 120: parser.error("等待資料重試必須5至120分鐘")
    backfill_runner = None
    if args.backfill_missing and args.mode == "live":
        # Ensure the isolated research database exists even if the scanner
        # has not yet completed its first collection cycle.
        from collector import connect as connect_research_db
        connect_research_db(args.state_dir).close()
        from agent_history_backfill import backfill_once
        def backfill_runner(state_dir, symbol, interval):
            return backfill_once(state_dir, symbol, interval, pages=10)
    proposal_runner = None
    if args.proposal_research:
        from agent_state_proposals import research_from_state
        proposal_runner = research_from_state
    from agent_single_instance import research_lock, AlreadyRunning
    try:
        with research_lock(args.state_dir):
            from agent_research_cursor import read_cursor,save_cursor,fully_completed,failed_symbols
            from agent_research_pending import load_pending,save_pending,clear_pending
            from agent_research_batch_evidence import save_batch_evidence
            batch_number = read_cursor(args.state_dir) if args.auto_universe else 0
            while True:
                started_at = datetime.now(timezone.utc).isoformat()
                write_status(args.state_dir, {
                    "schema": "agent-scheduler-v1", "paper_only": True,
                    "live_trading_authorized": False, "phase": "running",
                    "started_at": started_at, "items": []})
                try:
                    if args.auto_universe:
                        from agent_research_universe import next_batch
                        current_symbols = load_pending(args.state_dir,batch_number) or next_batch(args.state_dir,args.interval,args.mode,batch_number=batch_number)
                    else:
                        current_symbols = tuple(args.symbols)
                    if not current_symbols:
                        result = {"schema":"agent-scheduler-v1","paper_only":True,
                                  "live_trading_authorized":False,"items":[],
                                  "finished_at":datetime.now(timezone.utc).isoformat(),
                                  "data_waiting":True}
                    else:
                        result = run_once(args.state_dir,current_symbols,args.interval,args.mode,
                                          proposal_runner=proposal_runner,
                                          backfill_runner=backfill_runner)
                        if args.auto_universe:
                            save_batch_evidence(args.state_dir,batch_number,result)
                            if fully_completed(result):
                                # Clear completed retries first; on crash, a
                                # repeated safe batch is better than a stale
                                # pending file locking the next batch.
                                clear_pending(args.state_dir)
                                batch_number += 1
                                save_cursor(args.state_dir,batch_number)
                            else:
                                pending=failed_symbols(result)
                                if pending:
                                    save_pending(args.state_dir,batch_number,pending)
                    # Review a bounded number of previously frozen candidates
                    # using only newly closed candles. Observations are
                    # diagnostics, never input for strategy promotion.
                    if args.auto_universe and args.mode=="live":
                        from agent_forward_batch import review_frozen_batch
                        result["forward_paper_review"]=review_frozen_batch(
                            args.state_dir,limit=3,batch_number=batch_number)
                        # At most one deteriorated symbol is re-researched on
                        # currently available candles. This is never promotion,
                        # execution, or proof of improvement.
                        requests=[x["research_recheck"] for x in
                                  result["forward_paper_review"]["items"]
                                  if isinstance(x.get("research_recheck"),dict)
                                  and x["research_recheck"].get("interval")==args.interval]
                        if requests:
                            symbol=requests[0]["symbol"]
                            result["deterioration_research"]=run_once(
                                args.state_dir,(symbol,),args.interval,args.mode,
                                proposal_runner=None,backfill_runner=None)
                            from agent_recheck_comparison import compare_research_recheck
                            result["deterioration_comparison"]=compare_research_recheck(
                                args.state_dir,
                                next(x["reference_sha256"] for x in
                                     result["forward_paper_review"]["items"]
                                     if x.get("research_recheck") is requests[0]),
                                result["deterioration_research"])
                            from agent_fair_paper_queue import save_comparison_request
                            result["comparison_request"]=save_comparison_request(
                                args.state_dir,symbol,args.interval,
                                result["deterioration_comparison"])
                    if args.auto_universe and args.mode=="live":
                        from agent_fair_paper_queue import review_comparison_requests
                        result["fair_paper_comparisons"]=review_comparison_requests(
                            args.state_dir,limit=2,batch_number=batch_number)
                    result["phase"] = "completed"
                    if args.auto_universe:
                        result["next_batch"] = batch_number
                    result["started_at"] = started_at
                except Exception as exc:
                    # Process-level failure must be visible, not silently misreported.
                    result = {"schema": "agent-scheduler-v1", "paper_only": True,
                              "live_trading_authorized": False, "phase": "error",
                              "started_at": started_at,
                              "finished_at": datetime.now(timezone.utc).isoformat(),
                              "error_type": type(exc).__name__, "items": []}
                target=write_status(args.state_dir,result)
                print(json.dumps({"status_file":str(target),"phase":result["phase"],
                                  "items":result["items"]},ensure_ascii=False),flush=True)
                if args.once:break
                items=result.get("items",[])
                waiting=result.get("data_waiting",False) or (bool(items) and all(
                    x.get("error_type")=="DataNotReady" for x in items))
                time.sleep(args.retry_minutes*60 if waiting else args.hours*3600)
    except AlreadyRunning as exc:
        print(str(exc), flush=True)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

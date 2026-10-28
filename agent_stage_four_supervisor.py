"""Bounded opt-in Stage 4 supervisor. Never places orders or runs without consent.

The user explicitly budgets at most 10 model proposals per batch. Each UTC
slot is unique; the rotation checkpoint prevents replay. An expected lack of
fresh data is a normal wait, while ambiguous work halts for manual review.
"""
import argparse
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from agent_stage_four_periodic import utc_slot
from agent_stage_four_rotation import run_rotation


def _status(state_dir, *, phase, slot="", completed_batches=0, max_calls=0):
    root=Path(state_dir)
    root.mkdir(parents=True,exist_ok=True)
    target=root/"supervisor-status.json"
    data={"schema":"agent-stage4-supervisor-status-v1","phase":phase,
          "slot":slot,"completed_batches":completed_batches,
          "max_model_calls_authorized":max_calls,
          "updated_at_utc":datetime.now(timezone.utc).isoformat(),
          "paper_only":True,"live_trading_authorized":False}
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=root,
                                     delete=False,suffix=".tmp") as stream:
        json.dump(data,stream,sort_keys=True,ensure_ascii=False,allow_nan=False)
        temporary=stream.name
    os.replace(temporary,target)


def supervise(state_dir, *, max_batches, hours=6, interval="1h",
              model="gpt-4.1-mini", count=1600, runner=run_rotation,
              clock=None, sleep=None):
    if type(max_batches) is not int or not 1 <= max_batches <= 24:
        raise ValueError("Must explicitly cap model batches to 1..24")
    if hours not in (1, 2, 3, 4, 6, 8, 12, 24):
        raise ValueError("Invalid UTC period")
    if interval not in ("15m", "1h", "4h") or type(count) is not int or not 100 <= count <= 1600:
        raise ValueError("Invalid interval or closed-candle history limit")
    if not os.getenv("OPENAI_API_KEY") and runner is run_rotation:
        raise ValueError("OPENAI_API_KEY is required before starting paid AI research")
    clock = clock or (lambda: datetime.now(timezone.utc))
    sleep = sleep or time.sleep
    # Never repeat already attempted slots following a process restart.
    # The rotation cursor remains the authoritative ledger for billing.
    ledger=Path(state_dir)/"stage4-universe-cursor.json"
    if ledger.is_file():
        if ledger.stat().st_size>4096:
            raise ValueError("Oversized persisted research cursor")
        previous=json.loads(ledger.read_text(encoding="utf-8"))
        if previous.get("schema")!="agent-stage4-universe-cursor-v1" or previous.get("live_trading_authorized") is not False:
            raise ValueError("Invalid persisted research cursor")
        if previous.get("status")=="reserved":
            _status(state_dir,phase="requires_manual_review",
                    slot=str(previous.get("slot",""))[:48],max_calls=10*max_batches)
            raise ValueError("Interrupted research slot requires manual review before paid work")
    attempted = set()
    outcomes = []
    max_calls=10*max_batches
    _status(state_dir,phase='running',max_calls=max_calls)
    # A restart with a previously completed slot must not consume an
    # authorized batch on the same UTC slot. The persisted cursor is the ledger.
    if ledger.is_file():
        prior=json.loads(ledger.read_text(encoding="utf-8"))
        current_slot=utc_slot(clock(),hours)
        if prior.get("slot")==current_slot and prior.get("status")=="completed":
            # This invocation exits immediately: do not claim a waiting
            # supervisor is alive when no worker will wake for the next slot.
            _status(state_dir,phase="completed",slot=current_slot,
                    max_calls=max_calls)
            # A restart cannot replay work already billed during this slot.
            # Stop this invocation: a new explicit session is required to
            # authorize additional future work.
            return {"schema":"agent-stage4-bounded-supervisor-v1",
                    "max_model_calls_authorized":max_calls,
                    "attempted_slots":[{"slot":current_slot,"status":"already_processed"}],
                    "paper_only":True,"automatic_promotion":False,
                    "live_trading_authorized":False}
    for index in range(max_batches):
        now = clock()
        slot = utc_slot(now, hours)
        if slot in attempted:
            _status(state_dir,phase="error",slot=slot,
                    completed_batches=sum(x["status"]=="completed" for x in outcomes),
                    max_calls=max_calls)
            raise ValueError("UTC slot repeated; refusing duplicate billing")
        attempted.add(slot)
        try:
            result = runner(state_dir, slot=slot, interval=interval, model=model, count=count)
            status = result["status"]
            permitted = {"completed", "already_processed", "waiting_for_fresh_data",
                         "requires_manual_review", "empty_universe"}
            # Production exchange/provider output must explicitly attest its
            # safety boundary. Lightweight injected CI runners remain compatible.
            strict_provenance = runner is run_rotation
            if (status not in permitted or
                    result.get("live_trading_authorized", None if strict_provenance else False) is not False or
                    result.get("paper_only", None if strict_provenance else True) is not True):
                raise ValueError("Unsafe or unknown OpenAI research result; halting")
        except (KeyboardInterrupt, SystemExit):
            # An interrupted request may already have been billed.
            _status(state_dir,phase="requires_manual_review",slot=slot,
                    completed_batches=sum(x["status"]=="completed" for x in outcomes),
                    max_calls=max_calls)
            raise
        except Exception:
            # A failure after the request was sent may already have incurred
            # model charges. Do not display a safely retryable generic error.
            _status(state_dir,phase="requires_manual_review",slot=slot,
                    completed_batches=sum(x["status"]=="completed" for x in outcomes),
                    max_calls=max_calls)
            raise
        _status(state_dir,phase=status if status in
                ("waiting_for_fresh_data","requires_manual_review") else "running",
                slot=slot,completed_batches=len(outcomes)+(status=="completed"),
                max_calls=max_calls)
        outcomes.append({"slot": slot, "status": status})
        # A saved reservation means a prior paid request could be unresolved.
        # Do not schedule another slot after any ambiguous state.
        if status in ("requires_manual_review", "empty_universe"):
            break
        if index + 1 < max_batches:
            # Sleep to the next UTC slot. After a normal data-wait we will
            # re-check on a later slot without consuming any model calls.
            if status in ("completed","already_processed"):
                _status(state_dir,phase="waiting_for_next_slot",slot=slot,
                        completed_batches=sum(x["status"]=="completed" for x in outcomes),
                        max_calls=max_calls)
            current = clock()
            elapsed = ((current.hour % hours) * 3600 +
                       current.minute * 60 + current.second)
            delay=max(1, hours * 3600 - elapsed)
            if sleep is time.sleep:
                # Keep a genuine heartbeat while idle, without new model calls.
                # A previously displayed "running" state must never linger.
                deadline=time.monotonic()+delay
                while time.monotonic()<deadline:
                    phase=("waiting_for_fresh_data" if status=="waiting_for_fresh_data"
                           else "waiting_for_next_slot")
                    _status(state_dir,phase=phase,slot=slot,
                            completed_batches=sum(x["status"]=="completed" for x in outcomes),
                            max_calls=max_calls)
                    time.sleep(min(60, max(0,deadline-time.monotonic())))
            else:
                sleep(delay)
    if outcomes:
        final_status=outcomes[-1]["status"]
        phase=(final_status if final_status in ("requires_manual_review","waiting_for_fresh_data")
               else "error" if final_status=="empty_universe" else "completed")
        _status(state_dir,phase=phase,slot=outcomes[-1]["slot"],completed_batches=sum(x["status"]=="completed" for x in outcomes),max_calls=max_calls)
    return {"schema": "agent-stage4-bounded-supervisor-v1",
            "max_model_calls_authorized": 10 * max_batches,
            "attempted_slots": outcomes, "paper_only": True,
            "automatic_promotion": False, "live_trading_authorized": False}


def main():
    p = argparse.ArgumentParser(description="Explicitly bounded paid OpenAI research; no orders")
    p.add_argument("--state-dir", required=True)
    p.add_argument("--max-batches", required=True, type=int)
    p.add_argument("--ack-max-model-calls", required=True, type=int)
    p.add_argument("--hours", type=int, default=6)
    p.add_argument("--interval", default="1h")
    p.add_argument("--model", default="gpt-4.1-mini")
    a = p.parse_args()
    if a.ack_max_model_calls != a.max_batches * 10:
        p.error("Explicit model call acknowledgment must equal max-batches * 10")
    result = supervise(a.state_dir, max_batches=a.max_batches,
                       hours=a.hours, interval=a.interval, model=a.model)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

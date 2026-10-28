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


def supervise(state_dir, * max_batches, hours=6, interval="1h",
              model="gpt-4.1-mini", count=1600, runner=run_rotation,
              clock=None, sleep=None):
    if type(max_batches) is not int or not 1 <= max_batches <= 24:
        raise ValueError("Must explicitly cap model batches to 1..24")
    if hours not in (1, 2, 3, 4, 6, 8, 12, 24):
        raise ValueError("Invalid UTC period")
    if not os.getenv("OPENAI_API_KEY") and runner is run_rotation:
        raise ValueError("OPENAI_API_KEY is required before starting paid AI research")
    clock = clock or (lambda: datetime.now(timezone.utc))
    sleep = sleep or time.sleep
    attempted = set()
    outcomes = []
    max_calls=10*max_batches
    _status(state_dir,phase='running',max_calls=max_calls)
    for index in range(max_batches):
        now = clock()
        slot = utc_slot(now, hours)
        if slot in attempted:
            raise ValueError("UTC slot repeated; refusing duplicate billing")
        attempted.add(slot)
        try:
            result = runner(state_dir, slot=slot, interval=interval, model=model, count=count)
            status = result["status"]
        except Exception:
            _status(state_dir,phase="error",slot=slot,
                    completed_batches=len(outcomes),max_calls=max_calls)
            raise
        _status(state_dir,phase=status if status in
                ("waiting_for_fresh_data","requires_manual_review") else "running",
                slot=slot,completed_batches=len(outcomes)+(status=="completed"),
                max_calls=max_calls)
        outcomes.append({"slot": slot, "status": status})
        if status in ("requires_manual_review", "empty_universe"):
            break
        if index + 1 < max_batches:
            # Sleep to the next UTC slot. After a normal data-wait we will
            # re-check on a later slot without consuming any model calls.
            current = clock()
            elapsed = ((current.hour % hours) * 3600 +
                       current.minute * 60 + current.second)
            sleep(max(1, hours * 3600 - elapsed))
    if outcomes and outcomes[-1]["status"] not in ("requires_manual_review","empty_universe"):
        _status(state_dir,phase="completed",slot=outcomes[-1]["slot"],completed_batches=sum(x["status"]=="completed" for x in outcomes),max_calls=max_calls)
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

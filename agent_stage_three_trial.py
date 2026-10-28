"""Explicit local stage-three real-provider research trial.

Uses public Binance candles, bounded OpenAI research, and immutable evidence.
Never reads Binance secrets, connects accounts, or authorizes orders. An
unsuccessful hypothesis remains a research result, not a forced promotion.
"""
import argparse
import json
from pathlib import Path
from agent_binance_public_candles import download_public_candles
from agent_model_cycle import run_multigeneration_model_cycle
from agent_llm_adapter import openai_compatible_model
from agent_stage_three_acceptance import verify_stage_three

def run_stage_three_trial(root, *, symbol="BTCUSDT", interval="1h", model="gpt-4.1-mini",
                          count=1600, fetch=None, propose=None, generation_cutoffs=None):
    target=Path(root)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError("Choose a new empty research trial directory")
    if type(count) is not int or count < 1000 or count > 3000:
        raise ValueError("Full research trial requires 1000-3000 candles")
    target.mkdir(parents=True,exist_ok=True)
    dataset=download_public_candles(target/"market.csv",symbol=symbol,interval=interval,
                                    count=count,fetch=fetch)
    real_provider_calls=[]
    def real_provider(prompt):
        response=openai_compatible_model(prompt,model=model)
        real_provider_calls.append(True)  # Only a successful API response counts.
        return response
    provider=propose if propose is not None else real_provider
    # Require an independent 60%+ validation window for the second generation.
    cutoffs=generation_cutoffs if generation_cutoffs is not None else [max(300,int(count*.36)),count]
    result=run_multigeneration_model_cycle(dataset["csv"],target/"reports",
                   provider,model_id=model,cutoffs=cutoffs)
    # Model success alone is not stage completion. No external attestation is
    # injected here: the verifier must report incomplete when evidence is short.
    verified_live_provider=(propose is None and len(real_provider_calls)==result["completed_generations"] and len(real_provider_calls)>=2)
    check=verify_stage_three(result["reports"],live_provider_verified=verified_live_provider)
    summary={"schema":"agent-stage-three-local-trial-v1","market":dataset,
             "model":model,"research":result,"acceptance":check,
             "provider_verified_by_live_calls":verified_live_provider,
             "paper_only":True,"live_trading_authorized":False}
    (target/"trial_summary.json").write_text(
        json.dumps(summary,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+"\n",
        encoding="utf-8")
    return summary

def main():
    parser=argparse.ArgumentParser(description="Public market + real LLM offline research trial")
    parser.add_argument("--out",required=True)
    parser.add_argument("--symbol",default="BTCUSDT")
    parser.add_argument("--interval",default="1h")
    parser.add_argument("--model",default="gpt-4.1-mini")
    parser.add_argument("--count",type=int,default=1600)
    args=parser.parse_args()
    result=run_stage_three_trial(args.out,symbol=args.symbol,interval=args.interval,
                                 model=args.model,count=args.count)
    print(json.dumps({"trial_summary":str(Path(args.out)/"trial_summary.json"),
           "completed_generations":result["research"]["completed_generations"],
           "stop_reason":result["research"]["stop_reason"],
           "stage_three_accepted":result["acceptance"]["accepted"],
           "paper_only":True,"live_trading_authorized":False},ensure_ascii=False))

if __name__=="__main__":
    main()

"""Explicit safe connectivity check for the B+C research model.

Reads OPENAI_API_KEY from the local environment only. Never prints the key,
never contacts Binance account endpoints, and never places orders.
"""
import argparse
import json
import os
from agent_llm_adapter import openai_compatible_model

def verify_model_connection(*, model="gpt-4.1-mini", dry_run=False, provider=None):
    if not isinstance(model,str) or not 1 <= len(model) <= 100:
        raise ValueError("Invalid model identifier")
    if not dry_run and not os.environ.get("OPENAI_API_KEY") and provider is None:
        raise ValueError("Set OPENAI_API_KEY locally; never upload it")
    if dry_run:
        return {"status":"configuration_only","model":model,"model_called":False,
                "paper_only":True,"live_trading_authorized":False}
    invoke=provider if provider is not None else lambda prompt:openai_compatible_model(prompt,model=model)
    response=invoke("Return exactly one JSON array with one trend strategy: family trend, lookback 10, slow 50, rationale connectivity test.")
    if not isinstance(response,str) or len(response.encode("utf-8"))>16384:
        raise ValueError("Model response invalid")
    from agent_strategy_proposals import validate
    proposals=json.loads(response)
    if not isinstance(proposals,list) or len(proposals)!=1:
        raise ValueError("Expected exactly one model proposal")
    validate(proposals[0])
    return {"status":"model_proposal_received","model":model,"model_called":True,
            "bounded_strategy_valid":True,"paper_only":True,
            "live_trading_authorized":False}

def main():
    parser=argparse.ArgumentParser(description="One-call AI research connectivity verification")
    parser.add_argument("--model",default="gpt-4.1-mini")
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    print(json.dumps(verify_model_connection(model=args.model,dry_run=args.dry_run),
                     ensure_ascii=False))
if __name__=="__main__":
    main()

"""Opt-in OpenAI-compatible chat model adapter for offline strategy research.

Only used when explicitly invoked. Credentials are read from the environment,
never stored in evidence files. No tools, command execution or trading access.
"""
import argparse
import json
import os
import urllib.request
import urllib.error
from urllib.parse import urlsplit
from pathlib import Path
from agent_model_feedback import research_with_feedback
from agent_model_research import model_research

MAX_BODY = 32768

# Strict structured output with object root; unwrap proposals for existing callers.
PROPOSAL_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "bounded_research_proposals",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "proposals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "family": {"type": "string", "enum": ["trend", "breakout"]},
                            "lookback": {"type": "integer"},
                            "slow": {"type": "integer"},
                            "rationale": {"type": "string"}
                        },
                        "required": ["family", "lookback", "slow", "rationale"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["proposals"],
            "additionalProperties": False
        }
    }
}

def openai_compatible_model(prompt, *, model, api_key=None, endpoint="https://api.openai.com/v1/chat/completions"):
    parsed=urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Model endpoint must use a valid HTTPS URL")
    if not isinstance(model,str) or not model or len(model)>100:
        raise ValueError("Invalid model")
    secret=api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
    if not isinstance(secret,str) or not secret.strip():
        raise ValueError("OPENAI_API_KEY is required for model calls")
    if not isinstance(prompt,str) or len(prompt.encode("utf-8"))>12000:
        raise ValueError("Prompt too large")
    request_body=json.dumps({
        "model":model, "temperature":0,
        "response_format": PROPOSAL_FORMAT,
        "messages":[
            {"role":"system","content":"Return a JSON object with proposals containing 1-12 strategies. Each strategy has exactly family, lookback, slow, rationale. For trend use lookback 5-60 and slow at least lookback+5 up to 160; for breakout use lookback 5-60 and slow 0. No code, tools or orders."},
            {"role":"user","content":prompt}
        ]},ensure_ascii=False).encode("utf-8")
    request=urllib.request.Request(endpoint,data=request_body,
        headers={"Authorization":"Bearer "+secret, "Content-Type":"application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            body=response.read(MAX_BODY+1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        # Never expose provider error payloads or authorization headers.
        raise RuntimeError("Model request failed; no research report saved") from None
    if len(body)>MAX_BODY:
        raise ValueError("Model response too large")
    try:
        data=json.loads(body)
        text=data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ValueError("Malformed model response") from None
    if not isinstance(text,str):
        raise ValueError("Model response missing text")
    from agent_strategy_proposals import validate
    try:
        wrapped=json.loads(text)
        proposals=wrapped["proposals"]
        if not isinstance(proposals,list) or not 1 <= len(proposals) <= 12:
            raise ValueError("Invalid proposal count")
        for proposal in proposals:
            validate(proposal)
    except (ValueError,TypeError,KeyError):
        raise ValueError("Model proposals violate strict research schema") from None
    return json.dumps(proposals,ensure_ascii=False)

def main():
    parser=argparse.ArgumentParser(description="Opt-in model strategy hypotheses; paper research only")
    parser.add_argument("csv")
    parser.add_argument("--out",required=True)
    parser.add_argument("--model",required=True)
    parser.add_argument("--prior",help="Previous research report, for feedback on new data")
    parser.add_argument("--dry-run",action="store_true",help="Verify local input and configuration without contacting the model")
    args=parser.parse_args()
    if args.dry_run:
        from agent_csv_research import read_candles
        candles, fingerprint=read_candles(args.csv)
        if args.prior:
            from agent_model_feedback import check_feedback_readiness
            prior=json.loads(Path(args.prior).read_text(encoding="utf-8"))
            readiness=check_feedback_readiness(args.csv,prior)
            if readiness["dataset_sha256"] != fingerprint:
                raise ValueError("Dataset changed during preflight")
        print(json.dumps({"status":"local_inputs_validated","candles":len(candles),
                          "dataset_sha256":fingerprint,"model_called":False,
                          "paper_only":True,"live_trading_authorized":False},
                         ensure_ascii=False))
        return
    provider=lambda prompt:openai_compatible_model(prompt,model=args.model)
    if args.prior:
        prior=json.loads(Path(args.prior).read_text(encoding="utf-8"))
        result=research_with_feedback(args.csv,args.out,provider,model_id=args.model,prior=prior)
    else:
        result=model_research(args.csv,args.out,provider,model_id=args.model)
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    main()

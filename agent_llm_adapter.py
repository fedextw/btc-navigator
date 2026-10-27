"""Opt-in OpenAI-compatible chat model adapter for offline strategy research.

Only used when explicitly invoked. Credentials are read from the environment,
never stored in evidence files. No tools, command execution or trading access.
"""
import argparse
import json
import os
import urllib.request
from pathlib import Path
from agent_model_feedback import research_with_feedback
from agent_model_research import model_research

MAX_BODY = 32768

def openai_compatible_model(prompt, *, model, api_key=None, endpoint="https://api.openai.com/v1/chat/completions"):
    if not endpoint.startswith("https://"):
        raise ValueError("Model endpoint must use HTTPS")
    if not isinstance(model,str) or not model or len(model)>100:
        raise ValueError("Invalid model")
    secret=api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
    if not isinstance(secret,str) or not secret.strip():
        raise ValueError("OPENAI_API_KEY is required for model calls")
    if not isinstance(prompt,str) or len(prompt.encode("utf-8"))>12000:
        raise ValueError("Prompt too large")
    request_body=json.dumps({
        "model":model, "temperature":0,
        "messages":[
            {"role":"system","content":"Return a strict JSON array of bounded strategy parameters only. Do not include code, tools, or orders."},
            {"role":"user","content":prompt}
        ]},ensure_ascii=False).encode("utf-8")
    request=urllib.request.Request(endpoint,data=request_body,
        headers={"Authorization":"Bearer "+secret, "Content-Type":"application/json"},
        method="POST")
    with urllib.request.urlopen(request,timeout=30) as response:
        body=response.read(MAX_BODY+1)
    if len(body)>MAX_BODY:
        raise ValueError("Model response too large")
    data=json.loads(body)
    text=data["choices"][0]["message"]["content"]
    if not isinstance(text,str):
        raise ValueError("Model response missing text")
    return text

def main():
    parser=argparse.ArgumentParser(description="Opt-in model strategy hypotheses; paper research only")
    parser.add_argument("csv")
    parser.add_argument("--out",required=True)
    parser.add_argument("--model",required=True)
    parser.add_argument("--prior",help="Previous research report, for feedback on new data")
    args=parser.parse_args()
    provider=lambda prompt:openai_compatible_model(prompt,model=args.model)
    if args.prior:
        prior=json.loads(Path(args.prior).read_text(encoding="utf-8"))
        result=research_with_feedback(args.csv,args.out,provider,model_id=args.model,prior=prior)
    else:
        result=model_research(args.csv,args.out,provider,model_id=args.model)
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    main()

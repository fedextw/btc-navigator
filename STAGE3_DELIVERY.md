# B＋C Stage 3 — Integrated delivery and acceptance

**Scope:** independent research sandbox only; never merge into production or authorize trading.

## Completed engineering components
- Public Binance USD-M historical candle snapshot with hash and strict UTC candle checks
- Real OpenAI structured bounded hypothesis proposal; three vetted strategy families
- Chronologically separated validation, cost-adjusted paper evaluation, immutable reports
- Two-generation failure feedback, content-linked lineage, rejected-candidate continuation
- Explicit research resume with independent new market evidence
- Fixed-dataset, equal-cost model A/B comparison with per-model evidence
- Combined runner with final delivery summary

## Single-command local engineering acceptance
In a **fresh checkout** with configured `OPENAI_API_KEY`:

```powershell
py -3 agent_stage_three_delivery.py --out ".local-state\stage3-delivery-01" --symbol BTCUSDT --interval 1h --count 1600 --model gpt-4.1-mini --comparison-models gpt-4.1-mini gpt-5.4-mini
```

This action downloads public market data and performs **five potentially billable OpenAI model research calls** (two-generation trial + two model comparison calls + one research resume call). If the provider returns more/fewer valid generations or a provider call fails, the script fails closed. The user's own API access/billing must be configured locally; CI cannot prove real-provider connectivity. Never upload API secrets.

Review `.local-state\stage3-delivery-01\delivery_summary.json`, `trial/trial_summary.json`, `trial/reports/`, `comparison/comparison_summary.json`, and `comparison/model_*/`.

## Engineering acceptance versus profitability
- Engineering acceptance: two real model-backed generations, a real provider-backed recovery generation, valid chronological lineage, provider evidence recorded on live path, same frozen dataset for A/B, Windows/Linux CI green
- Profitability acceptance: **not established by Stage 3**; requires longer independent forward/paper evaluation after costs and realistic slippage, without selection leakage
- `live_trading_authorized` must remain `false` everywhere.
- No candidate can be automatically live-promoted.

## Remaining blocking verification
1. Windows/Linux latest GitHub Actions success on final commit
2. User-side genuine OpenAI model trial using local credentials
3. User-side model A/B including newer model access, availability and structured-output compatibility
4. Local resume test using a prior immutable failed report and **fresh chronologically independent candles**. The runner now pre-registers three non-overlapping validation windows from one immutable historical snapshot: generation 1, generation 2 and independently reserved recovery validation. It resumes automatically using that reserved later window. Optional `--resume-csv` can override the reserved data with a truly newer independent dataset. Reusing the earlier validation window is forbidden.

Do not mark Stage 3 fully delivered until blocking evidence has been collected. Do not claim profitable trading from engineering acceptance.
